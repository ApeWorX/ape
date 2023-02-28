import os.path
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, List, Optional

import yaml
from ethpm_types import Checksum, ContractType, PackageManifest, Source
from ethpm_types.manifest import PackageName
from ethpm_types.utils import AnyUrl, compute_checksum
from packaging.version import InvalidVersion, Version
from pydantic import ValidationError

from ape.logging import logger
from ape.utils import (
    BaseInterfaceModel,
    abstractmethod,
    cached_property,
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

    config_file_name: str = "ape-config.yaml"

    _cached_manifest: Optional[PackageManifest] = None

    _contracts: Optional[Dict[str, ContractType]] = None

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
        if self._cached_manifest is None:
            self._cached_manifest = _load_manifest_from_file(self.manifest_cachefile)
            if self._cached_manifest is None:
                return None

        manifest = self._cached_manifest
        if manifest.contract_types and not self.contracts:
            # Extract contract types from cached manifest.
            # This helps migrate to >= 0.6.3.
            # TODO: Remove once Ape 0.7 is released.
            for contract_type in manifest.contract_types.values():
                if not contract_type.name:
                    continue

                path = self._cache_folder / f"{contract_type.name}.json"
                path.write_text(contract_type.json())

            # Rely on individual cache files.
            self._contracts = manifest.contract_types
            manifest.contract_types = {}

        else:
            manifest.contract_types = self.contracts

        return manifest

    @property
    def contracts(self) -> Dict[str, ContractType]:
        if self._contracts is None:
            contracts = {}
            for p in self._cache_folder.glob("*.json"):
                if p == self.manifest_cachefile:
                    continue

                contract_name = p.stem
                contract_type = ContractType().parse_file(p)
                if contract_type.name is None:
                    contract_type.name = contract_name

                contracts[contract_type.name] = contract_type
            self._contracts = contracts
        return self._contracts

    @property
    def _cache_folder(self) -> Path:
        folder = self.contracts_folder.parent / ".build"
        # NOTE: If we use the cache folder, we expect it to exist
        folder.mkdir(exist_ok=True, parents=True)
        return folder

    def process_config_file(self, **kwargs) -> bool:
        """
        Process the project's config file.
        Returns ``True`` if had to create a temporary ``ape-config.yaml`` file.
        """

        return False

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
    the manifest for this dependency.

    **NOTE**: This must be the name of a directory in the project.
    """

    exclude: List[str] = ["package.json", "package-lock.json"]
    """
    A list of glob-patterns for excluding files in dependency projects.
    """

    _cached_manifest: Optional[PackageManifest] = None

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
    @abstractmethod
    def uri(self) -> AnyUrl:
        """
        The URI to use when listing in a PackageManifest.
        """

    @cached_property
    def _base_cache_path(self) -> Path:
        version_id = self.version_id

        try:
            _ = Version(version_id)  # Will raise if can't parse
            if not version_id.startswith("v"):
                version_id = f"v{version_id}"
        except InvalidVersion:
            pass

        return self.config_manager.packages_folder / self.name / version_id

    @property
    def _target_manifest_cache_file(self) -> Path:
        return self._base_cache_path / f"{self.name}.json"

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
        if self._cached_manifest is None:
            self._cached_manifest = _load_manifest_from_file(self._target_manifest_cache_file)
        return self._cached_manifest

    def __getitem__(self, contract_name: str) -> "ContractContainer":
        try:
            container = self.get(contract_name)
        except Exception as err:
            raise IndexError(str(err)) from err

        if not container:
            raise IndexError(f"Contract '{contract_name}' not found.")

        return container

    def __getattr__(self, contract_name: str) -> "ContractContainer":
        try:
            return self.__getattribute__(contract_name)
        except AttributeError:
            pass

        try:
            container = self.get(contract_name)
        except Exception as err:
            raise AttributeError(
                f"Dependency project '{self.name}' has no contract "
                f"or attribute '{contract_name}'.\n{err}"
            ) from err

        if not container:
            raise AttributeError(
                f"Dependency project '{self.name}' has no contract '{contract_name}'."
            )

        return container

    def get(self, contract_name: str) -> Optional["ContractContainer"]:
        manifest = self.compile()
        if hasattr(manifest, contract_name):
            contract_type = getattr(manifest, contract_name)
            return self.chain_manager.contracts.get_container(contract_type)

        return None

    def compile(self) -> PackageManifest:
        """
        Compile the contract types in this dependency into
        a package manifest.

        **NOTE**: By default, dependency's compile lazily.
        """

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

                # Create content, including sub-directories.
                source_path.parent.mkdir(parents=True, exist_ok=True)
                source_path.touch()
                source_path.write_text(content)

            # Handle import remapping entries indicated in the manifest file
            target_config_file = project.path / project.config_file_name
            packages_used = set()
            config_data: Dict[str, Any] = {}
            for compiler in [x for x in manifest.compilers or [] if x.settings]:
                name = compiler.name.lower()
                compiler_data = {}
                settings = compiler.settings or {}
                remapping_list = []
                for remapping in settings.get("remappings") or []:
                    parts = remapping.split("=")
                    key = parts[0]
                    link = parts[1]
                    if link.startswith(f".cache{os.path.sep}"):
                        link = os.path.sep.join(link.split(f".cache{os.path.sep}"))[1:]

                    packages_used.add(link)
                    new_entry = f"{key}={link}"
                    remapping_list.append(new_entry)

                if remapping_list:
                    compiler_data["import_remapping"] = remapping_list

                if compiler_data:
                    config_data[name] = compiler_data

            # Handle dependencies indicated in the manifest file
            dependencies_config: List[Dict] = []
            dependencies = manifest.dependencies or {}
            dependencies_used = {
                p: d for p, d in dependencies.items() if any(p.lower() in x for x in packages_used)
            }
            for package_name, uri in dependencies_used.items():
                if "://" not in str(uri) and hasattr(uri, "scheme"):
                    uri_str = f"{uri.scheme}://{uri}"
                else:
                    uri_str = str(uri)

                dependency = {"name": str(package_name)}
                if uri_str.startswith("https://"):
                    # Assume GitHub dependency
                    version = uri_str.split("/")[-1]
                    dependency["github"] = uri_str.replace(f"/releases/tag/{version}", "")
                    dependency["github"] = dependency["github"].replace("https://github.com/", "")
                    dependency["version"] = version

                elif uri_str.startswith("file://"):
                    dependency["local"] = uri_str.replace("file://", "")

                dependencies_config.append(dependency)

            if dependencies_config:
                config_data["dependencies"] = dependencies_config

            if config_data:
                target_config_file.unlink(missing_ok=True)
                with open(target_config_file, "w+") as cf:
                    yaml.safe_dump(config_data, cf)

            manifest = project.create_manifest()
            self._write_manifest_to_cache(manifest)
            return manifest

    def _extract_local_manifest(self, project_path: Path) -> PackageManifest:
        cached_manifest = (
            _load_manifest_from_file(self._target_manifest_cache_file)
            if self._target_manifest_cache_file.is_file()
            else None
        )
        if cached_manifest:
            return cached_manifest

        # NOTE: Dependencies are not compiled here. Instead, the sources are packaged
        # for later usage via imports. For legacy reasons, many dependency-esque projects
        # are not meant to compile on their own.

        with self.config_manager.using_project(
            project_path,
            contracts_folder=(project_path / self.contracts_folder).expanduser().resolve(),
        ):
            project = self._get_project(project_path)
            sources = self._get_sources(project)
            dependencies = self.project_manager._extract_manifest_dependencies()
            project_manifest = project._create_manifest(
                sources, project.contracts_folder, {}, name=project.name, version=project.version
            )
            compiler_data = self.project_manager._get_compiler_data(compile_if_needed=False)

        if dependencies:
            project_manifest.dependencies = dependencies
        if compiler_data:
            project_manifest.compilers = compiler_data

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
        self._cached_manifest = manifest


def _load_manifest_from_file(file_path: Path) -> Optional[PackageManifest]:
    if not file_path.is_file():
        return None

    try:
        return PackageManifest.parse_file(file_path)
    except ValidationError as err:
        logger.warning(f"Existing manifest file '{file_path}' corrupted. Re-building.")
        logger.debug(str(err))
        return None
