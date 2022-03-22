import json
from pathlib import Path
from typing import TYPE_CHECKING, Collection, Dict, List, Optional

from ethpm_types import Checksum, ContractType, PackageManifest, Source
from ethpm_types.manifest import PackageName
from ethpm_types.utils import compute_checksum
from packaging import version as version_util
from pydantic import ValidationError

from ape.exceptions import ProjectError
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
            file_paths (Optional[List]): An optional list of paths to compile
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
        sources: Collection[Path],
        contracts_path: Path,
        contract_types: Dict[str, ContractType],
        name: Optional[str] = None,
        version: Optional[str] = None,
        initial_manifest: Optional[PackageManifest] = None,
    ) -> PackageManifest:
        manifest = initial_manifest or PackageManifest()

        if name:
            manifest.name = PackageName(name.lower())

        if version:
            manifest.version = version

        manifest.sources = cls._create_source_dict(sources, contracts_path)
        manifest.contract_types = contract_types
        return PackageManifest(**manifest.dict())

    @classmethod
    def _create_source_dict(
        cls, contract_paths: Collection[Path], base_path: Path
    ) -> Dict[str, Source]:
        return {
            str(get_relative_path(source, base_path)): Source(  # type: ignore
                checksum=Checksum(  # type: ignore
                    algorithm="md5",
                    hash=compute_checksum(source.read_bytes()),
                ),
                urls=[],
                content=source.read_text(),
            )
            for source in contract_paths
        }


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
        if isinstance(
            version_util.parse(version_id), version_util.Version
        ) and not version_id.startswith("v"):
            version_id = f"v{version_id}"

        name = self.name
        return self.config_manager.packages_folder / name / version_id / f"{name}.json"

    @abstractmethod
    def extract_manifest(self) -> PackageManifest:
        """
        Create a :class:`~ape.api.projects.ProjectAPI` implementation,
        presumably by downloading and compiling the dependency.

        Implementations may use ``self.project_manager`` to call method
        :meth:`~ape.managers.project.ProjectManager.get_project`
        to dynamically get the correct :class:`~ape.api.projects.ProjectAPI`.
        based on the project's structure.

        Returns:
            :class:`~ape.api.projects.ProjectAPI`
        """

    @property
    def cached_manifest(self) -> Optional[PackageManifest]:
        """
        The manifest from the ``.ape/packages/<dependency-name>/<version-id>``
        if it exists and is valid.
        """
        return _load_manifest_from_file(self._target_manifest_cache_file)

    def __getattr__(self, item: str) -> "ContractContainer":
        manifest = self.extract_manifest()
        if hasattr(manifest, item):
            return self.create_contract_container(contract_type=getattr(manifest, item))

        raise ProjectError(f"Dependency project '{self.name}' has no contract '{item}'.")

    def _extract_local_manifest(self, project_path: Path):
        project_path = project_path.resolve()
        contracts_folder = project_path / self.contracts_folder
        project = self.project_manager.get_project(
            project_path,
            contracts_folder=contracts_folder,
            name=self.name,
            version=self.version,
        )

        all_sources = get_all_files_in_directory(project.contracts_folder)

        excluded_files = set()
        for pattern in set(self.exclude):
            excluded_files.update({f for f in project.contracts_folder.glob(pattern)})

        sources = [s for s in all_sources if s not in excluded_files]
        project_manifest = project.create_manifest(file_paths=sources)

        if not project_manifest.contract_types:
            raise ProjectError(
                f"No contract types found in dependency '{self.name}'. "
                "Do you have the correct compilers installed?"
            )

        # Cache the manifest for future use outside of this tempdir.
        self._target_manifest_cache_file.parent.mkdir(exist_ok=True, parents=True)
        self._target_manifest_cache_file.write_text(json.dumps(project_manifest.dict()))

        return project_manifest


def _load_manifest_from_file(file_path: Path) -> Optional[PackageManifest]:
    if not file_path.exists():
        return None

    try:
        manifest_dict = json.loads(file_path.read_text())
        if not isinstance(manifest_dict, dict) or "manifest" not in manifest_dict:
            raise AssertionError()  # To reach except block

        return PackageManifest(**manifest_dict)

    except (AssertionError, json.JSONDecodeError, ValidationError):
        logger.warning(f"Existing manifest file '{file_path}' corrupted. Re-building.")
        return None
