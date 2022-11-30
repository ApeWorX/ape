import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Dict, List, Optional

from ethpm_types import Checksum, ContractType, PackageManifest, Source
from ethpm_types.manifest import PackageName
from ethpm_types.utils import compute_checksum
from packaging.version import InvalidVersion, Version
from pydantic import ValidationError

from ape.logging import logger
from ape.utils import (
    BaseInterfaceModel,
    abstractmethod,
    get_all_files_in_directory,
    get_relative_path,
)

if TYPE_CHECKING:
    from ape.contracts import ContractContainer


class ProjectAPI(BaseInterfaceModel):
    """
    An abstract base-class for working with projects.
    This class can also be extended to a plugin for supporting non-ape projects.
    """

    path: Path
    """The project path."""

    contracts_folder: Path
    """The path to the contracts in the project."""

    name: Optional[str] = None
    """The name of this project when another project uses it as a dependency."""

    version: Optional[str] = None
    """The version of the project whe another project uses it as a dependency."""

    def __repr__(self):
        return f"<{self.__class__.__name__} {self.path.name}>"

    @property
    @abstractmethod
    def is_valid(self) -> bool:
        """
        ``True`` if the project at the given path matches this project type.
        Useful for figuring out the best ``ProjectAPI`` to use when compiling a project.
        """

    @abstractmethod
    def create_manifest(
        self, file_paths: Optional[List[Path]] = None, use_cache: bool = True
    ) -> PackageManifest:
        """
        Create a manifest from the project.

        Args:
            file_paths (Optional[List[Path]]): An optional list of paths to compile
              from this project.
            use_cache (bool): Set to ``False`` to clear caches and force a re-compile.

        Returns:
            ``PackageManifest``
        """

    @property
    def manifest_cachefile(self) -> Path:
        """
        The path to the project's cached manifest. The manifest
        is a cached file representing the project and is useful
        for sharing, such as uploading to IPFS.

        Returns:
            pathlib.Path
        """

        file_name = self.name or "__local__"
        return self._cache_folder / f"{file_name}.json"

    @property
    def cached_manifest(self) -> Optional[PackageManifest]:
        """
        The ``PackageManifest`` at :py:attr:`~ape.api.projects.ProjectAPI.manifest_cachefile`
        if it exists and is valid.
        """

        return _load_manifest_from_file(self.manifest_cachefile)

    @property
    def _cache_folder(self) -> Path:
        folder = self.path / ".build"
        # NOTE: If we use the cache folder, we expect it to exist
        folder.mkdir(exist_ok=True, parents=True)
        return folder

    @classmethod
    def _create_manifest(
        cls,
        source_paths: List[Path],
        contracts_path: Path,
        contract_types: Dict[str, ContractType],
        name: Optional[str] = None,
        version: Optional[str] = None,
        initial_manifest: Optional[PackageManifest] = None,
    ) -> PackageManifest:
        manifest = initial_manifest or PackageManifest()
        manifest.name = PackageName(name.lower()) if name is not None else manifest.name
        manifest.version = version or manifest.version
        manifest.sources = cls._create_source_dict(source_paths, contracts_path)
        manifest.contract_types = contract_types
        return manifest

    @classmethod
    def _create_source_dict(
        cls, contract_filepaths: List[Path], base_path: Path
    ) -> Dict[str, Source]:
        source_imports: Dict[str, List[str]] = cls.compiler_manager.get_imports(
            contract_filepaths, base_path
        )  # {source_id: [import_source_ids, ...], ...}
        source_references: Dict[str, List[str]] = cls.compiler_manager.get_references(
            imports_dict=source_imports
        )  # {source_id: [referring_source_ids, ...], ...}

        source_dict: Dict[str, Source] = {}
        for source_path in contract_filepaths:
            key = str(get_relative_path(source_path, base_path))
            source_dict[key] = Source(
                checksum=Checksum(
                    algorithm="md5",
                    hash=compute_checksum(source_path.read_bytes()),
                ),
                urls=[],
                content=source_path.read_text("utf8"),
                imports=source_imports.get(key, []),
                references=source_references.get(key, []),
            )

        return source_dict  # {source_id: Source}


class DependencyAPI(BaseInterfaceModel):
    """
    A base-class for dependency sources, such as GitHub or IPFS.
    """

    name: str
    """The name of the dependency."""

    version: Optional[str] = None
    """
    The version of the dependency. Omit to use the latest.
    """

    contracts_folder: str = "contracts"
    """
    The name of the dependency's ``contracts/`` directory.
    This is where ``ape`` will look for source files when compiling
    the manifest for this dependency. **NOTE**: This must be the name
    of a directory in the project.
    """

    exclude: List[str] = ["package.json", "package-lock.json"]
    """
    A list of glob-patterns for excluding files in dependency projects.
    """

    def __repr__(self):
        return f"<{self.__class__.__name__} name='{self.name}'>"

    @property
    @abstractmethod
    def version_id(self) -> str:
        """
        The ID to use as the sub-directory in the download cache.
        Most often, this is either a version number or a branch name.
        """

    @property
    def _target_manifest_cache_file(self) -> Path:
        version_id = self.version_id

        try:
            _ = Version(version_id)  # Will raise if can't parse
            if not version_id.startswith("v"):
                version_id = f"v{version_id}"
        except InvalidVersion:
            pass

        name = self.name
        return self.config_manager.packages_folder / name / version_id / f"{name}.json"

    @abstractmethod
    def extract_manifest(self) -> PackageManifest:
        """
        Create a ``PackageManifest`` definition,
        presumably by downloading and compiling the dependency.

        Implementations may use ``self.project_manager`` to call method
        :meth:`~ape.managers.project.ProjectManager.get_project`
        to dynamically get the correct :class:`~ape.api.projects.ProjectAPI`.
        based on the project's structure.

        Returns:
            ``PackageManifest``
        """

    @property
    def cached_manifest(self) -> Optional[PackageManifest]:
        """
        The manifest from the ``.ape/packages/<dependency-name>/<version-id>``
        if it exists and is valid.
        """
        return _load_manifest_from_file(self._target_manifest_cache_file)

    def __getitem__(self, contract_name: str) -> "ContractContainer":
        container = self.get(contract_name)
        if not container:
            raise IndexError(f"Contract '{contract_name}' not found.")

        return container

    def __getattr__(self, contract_name: str) -> "ContractContainer":
        container = self.get(contract_name)
        if not container:
            raise AttributeError(
                f"Dependency project '{self.name}' has no contract '{contract_name}'."
            )

        return container

    def get(self, contract_name: str) -> Optional["ContractContainer"]:
        manifest = self._get_compiled_manifest()
        if hasattr(manifest, contract_name):
            contract_type = getattr(manifest, contract_name)
            return self.chain_manager.contracts.get_container(contract_type)

        return None

    def _get_compiled_manifest(self) -> PackageManifest:
        manifest = self.extract_manifest()
        if manifest.contract_types:
            # Already compiled
            return manifest

        sources = manifest.sources or {}  # NOTE: Already handled excluded files
        with tempfile.TemporaryDirectory() as temp_dir:
            project = self._get_project(Path(temp_dir))
            contracts_folder = project.contracts_folder.absolute()
            contracts_folder.mkdir(parents=True, exist_ok=True)
            for source_id, source_obj in sources.items():
                content = source_obj.content or ""
                absolute_path = contracts_folder / source_id
                source_path = contracts_folder / get_relative_path(
                    absolute_path, contracts_folder.absolute()
                )
                source_path.touch()
                source_path.write_text(content)

            manifest = project.create_manifest()
            self._write_manifest_to_cache(manifest)
            return manifest

    def _extract_local_manifest(self, project_path: Path):
        if self._target_manifest_cache_file.is_file():
            return PackageManifest.parse_file(self._target_manifest_cache_file)

        project = self._get_project(project_path)
        sources = self._get_sources(project)

        # NOTE: Dependencies are not compiled here. Instead, the sources are packaged
        # for later usage via imports. For legacy reasons, many dependency-esque projects
        # are not meant to compile on their own.
        project_manifest = project._create_manifest(
            sources, project.contracts_folder, {}, name=project.name, version=project.version
        )
        self._write_manifest_to_cache(project_manifest)
        return project_manifest

    def _get_sources(self, project: ProjectAPI) -> List[Path]:
        all_sources = get_all_files_in_directory(project.contracts_folder)

        excluded_files = set()
        for pattern in set(self.exclude):
            excluded_files.update({f for f in project.contracts_folder.glob(pattern)})

        return [s for s in all_sources if s not in excluded_files]

    def _get_project(self, project_path: Path) -> ProjectAPI:
        project_path = project_path.resolve()
        contracts_folder = project_path / self.contracts_folder
        return self.project_manager.get_project(
            project_path,
            contracts_folder=contracts_folder,
            name=self.name,
            version=self.version,
        )

    def _write_manifest_to_cache(self, manifest: PackageManifest):
        self._target_manifest_cache_file.unlink(missing_ok=True)
        self._target_manifest_cache_file.parent.mkdir(exist_ok=True, parents=True)
        self._target_manifest_cache_file.write_text(manifest.json())


def _load_manifest_from_file(file_path: Path) -> Optional[PackageManifest]:
    if not file_path.is_file():
        return None

    try:
        return PackageManifest.parse_file(file_path)
    except ValidationError as err:
        logger.warning(f"Existing manifest file '{file_path}' corrupted. Re-building.")
        logger.debug(str(err))
        return None
