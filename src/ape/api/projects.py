import os.path
import re
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Union

from ethpm_types import Checksum, Compiler, ContractType, PackageManifest, Source
from ethpm_types.manifest import PackageName
from ethpm_types.source import Content
from ethpm_types.utils import Algorithm, AnyUrl, compute_checksum
from packaging.version import InvalidVersion, Version

from ape._pydantic_compat import ValidationError
from ape.exceptions import ProjectError
from ape.logging import logger
from ape.utils import (
    BaseInterfaceModel,
    ExtraModelAttributes,
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
            contracts: Dict[str, ContractType] = {}

            # Exclude contracts with missing sources, else you'll get validation errors.
            # This scenario happens if changing branches and you have some contracts on
            # one branch and others on the next.
            for name, contract in self.contracts.items():
                source_id = contract.source_id
                if not contract.source_id:
                    continue

                if source_id in (manifest.sources or {}):
                    contracts[name] = contract

            manifest.contract_types = contracts

        return manifest

    @property
    def contracts(self) -> Dict[str, ContractType]:
        if self._contracts is not None:
            return self._contracts

        contracts = {}
        for p in self._cache_folder.glob("*.json"):
            if p == self.manifest_cachefile:
                continue

            contract_name = p.stem
            contract_type = ContractType.parse_file(p)
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
        compiler_data: Optional[List[Compiler]] = None,
    ) -> PackageManifest:
        manifest = initial_manifest or PackageManifest()
        manifest.name = PackageName(__root__=name.lower()) if name is not None else manifest.name
        manifest.version = version or manifest.version
        manifest.sources = cls._create_source_dict(source_paths, contracts_path)
        manifest.contract_types = contract_types
        manifest.compilers = compiler_data or []
        return manifest

    @classmethod
    def _create_source_dict(
        cls, contract_filepaths: Union[Path, List[Path]], base_path: Path
    ) -> Dict[str, Source]:
        filepaths = (
            [contract_filepaths] if isinstance(contract_filepaths, Path) else contract_filepaths
        )
        source_imports: Dict[str, List[str]] = cls.compiler_manager.get_imports(
            filepaths, base_path
        )  # {source_id: [import_source_ids, ...], ...}
        source_references: Dict[str, List[str]] = cls.compiler_manager.get_references(
            imports_dict=source_imports
        )  # {source_id: [referring_source_ids, ...], ...}

        source_dict: Dict[str, Source] = {}
        for source_path in filepaths:
            key = str(get_relative_path(source_path, base_path))

            try:
                text = source_path.read_text("utf8")
            except UnicodeDecodeError:
                # Let it attempt to find the encoding.
                # (this is much slower and a-typical).
                text = source_path.read_text()

            source_dict[key] = Source(
                checksum=Checksum(
                    algorithm=Algorithm.MD5,
                    hash=compute_checksum(source_path.read_bytes()),
                ),
                urls=[],
                content=Content(__root__={i + 1: x for i, x in enumerate(text.splitlines())}),
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

    exclude: List[str] = ["package.json", "package-lock.json", "**/.build/**/*.json"]
    """
    A list of glob-patterns for excluding files in dependency projects.
    """

    config_override: Dict = {}
    """
    Extra settings to include in the dependency's configuration.
    """

    _cached_manifest: Optional[PackageManifest] = None

    def __repr__(self):
        return f"<{self.__class__.__name__} name='{self.name}'>"

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        yield ExtraModelAttributes(
            name=self.name,
            attributes=self.contracts,
            include_getattr=True,
            include_getitem=True,
            additional_error_message="Do you have the necessary compiler plugins installed?",
        )

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
    def extract_manifest(self, use_cache: bool = True) -> PackageManifest:
        """
        Create a ``PackageManifest`` definition,
        presumably by downloading and compiling the dependency.

        Implementations may use ``self.project_manager`` to call method
        :meth:`~ape.managers.project.ProjectManager.get_project`
        to dynamically get the correct :class:`~ape.api.projects.ProjectAPI`.
        based on the project's structure.

        Args:
            use_cache (bool): Defaults to ``True``. Set to ``False`` to force
              a re-install.

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

    @cached_property
    def contracts(self) -> Dict[str, "ContractContainer"]:
        """
        A mapping of name to contract type of all the contracts
        in this dependency.
        """
        return {
            n: self.chain_manager.contracts.get_container(c)
            for n, c in (self.compile().contract_types or {}).items()
        }

    def get(self, contract_name: str) -> Optional["ContractContainer"]:
        return self.contracts.get(contract_name)

    def compile(self, use_cache: bool = True) -> PackageManifest:
        """
        Compile the contract types in this dependency into
        a package manifest.

        Args:
            use_cache (bool): Defaults to ``True``. Set to ``False`` to force
              a re-compile.

        **NOTE**: By default, dependency's compile lazily.
        """

        manifest = self.extract_manifest()
        if use_cache and manifest.contract_types:
            # Already compiled
            return manifest

        # Figure the config data needed to compile this dependency.
        # Use a combination of looking at the manifest's other artifacts
        # as well, config overrides, and the base project's config.
        config_data: Dict[str, Any] = {
            **_get_compile_configs_from_manifest(manifest),
            **_get_dependency_configs_from_manifest(manifest),
            **self.config_override,
        }

        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir)
            contracts_folder = path / config_data.get("contracts_folder", "contracts")
            with self.config_manager.using_project(
                path, contracts_folder=contracts_folder, **config_data
            ) as project:
                manifest.unpack_sources(contracts_folder)
                compiled_manifest = project.local_project.create_manifest()

                if not compiled_manifest.contract_types:
                    # Manifest is empty. No need to write to disk.
                    logger.warning(
                        "Compiled manifest produced no contract types! "
                        "Are you missing compiler plugins?"
                    )
                    return compiled_manifest

                self._write_manifest_to_cache(compiled_manifest)
                return compiled_manifest

    def _extract_local_manifest(
        self, project_path: Path, use_cache: bool = True
    ) -> PackageManifest:
        cached_manifest = (
            _load_manifest_from_file(self._target_manifest_cache_file)
            if use_cache and self._target_manifest_cache_file.is_file()
            else None
        )
        if cached_manifest:
            return cached_manifest

        if project_path.is_file() and project_path.suffix == ".json":
            try:
                manifest = PackageManifest.parse_file(project_path)

            except ValueError as err:
                if project_path.parent.is_dir():
                    project_path = project_path.parent

                else:
                    raise ProjectError(f"Invalid manifest file: '{project_path}'.") from err

            else:
                # Was given a path to a manifest JSON.
                self._write_manifest_to_cache(manifest)
                return manifest

        elif (project_path.parent / project_path.name.replace("-", "_")).is_dir():
            project_path = project_path.parent / project_path.name.replace("-", "_")

        elif (project_path.parent / project_path.name.replace("_", "-")).is_dir():
            project_path = project_path.parent / project_path.name.replace("_", "-")

        elif project_path.parent.is_dir():
            project_path = project_path.parent

        # NOTE: Dependencies are not compiled here. Instead, the sources are packaged
        # for later usage via imports. For legacy reasons, many dependency-esque projects
        # are not meant to compile on their own.

        with self.config_manager.using_project(
            project_path,
            contracts_folder=(project_path / self.contracts_folder).expanduser().resolve(),
        ) as pm:
            project = pm.local_project
            sources = self._get_sources(project)
            dependencies = self.project_manager._extract_manifest_dependencies()
            project_manifest = project._create_manifest(
                sources, project.contracts_folder, {}, name=project.name, version=project.version
            )
            compiler_data = self.project_manager.get_compiler_data(compile_if_needed=False)

        if dependencies:
            project_manifest.dependencies = dependencies
        if compiler_data:
            project_manifest.compilers = compiler_data

        self._write_manifest_to_cache(project_manifest)
        return project_manifest

    def _get_sources(self, project: ProjectAPI) -> List[Path]:
        escaped_extensions = [re.escape(ext) for ext in self.compiler_manager.registered_compilers]
        extension_pattern = "|".join(escaped_extensions)
        pattern = rf".*({extension_pattern})"
        all_sources = get_all_files_in_directory(project.contracts_folder, pattern=pattern)

        excluded_files = set()
        for pattern in set(self.exclude):
            excluded_files.update({f for f in project.contracts_folder.glob(pattern)})

        return [s for s in all_sources if s not in excluded_files]

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


def _get_compile_configs_from_manifest(manifest: PackageManifest) -> Dict[str, Dict]:
    configs: Dict[str, Dict] = {}
    for compiler in [x for x in manifest.compilers or [] if x.settings]:
        name = compiler.name.strip().lower()
        compiler_data = {}
        settings = compiler.settings or {}
        remapping_list = []
        for remapping in settings.get("remappings") or []:
            parts = remapping.split("=")
            key = parts[0]
            link = parts[1]
            if link.startswith(f".cache{os.path.sep}"):
                link = os.path.sep.join(link.split(f".cache{os.path.sep}"))[1:]

            new_entry = f"{key}={link}"
            remapping_list.append(new_entry)

        if remapping_list:
            compiler_data["import_remapping"] = remapping_list

        if "evm_version" in settings:
            compiler_data["evm_version"] = settings["evm_version"]

        if compiler_data:
            configs[name] = compiler_data

    return configs


def _get_dependency_configs_from_manifest(manifest: PackageManifest) -> Dict:
    dependencies_config: List[Dict] = []
    dependencies = manifest.dependencies or {}
    for package_name, uri in dependencies.items():
        if "://" not in str(uri) and hasattr(uri, "scheme"):
            uri_str = f"{uri.scheme}://{uri}"
        else:
            uri_str = str(uri)

        dependency: Dict = {"name": str(package_name)}
        if uri_str.startswith("https://"):
            # Assume GitHub dependency
            version = uri_str.split("/")[-1]
            dependency["github"] = uri_str.replace(f"/releases/tag/{version}", "")
            dependency["github"] = dependency["github"].replace("https://github.com/", "")

            # NOTE: If version fails, the dependency system will automatically try `ref`.
            dependency["version"] = version

        elif uri_str.startswith("file://"):
            dependency["local"] = uri_str.replace("file://", "")

        dependencies_config.append(dependency)

    return {"dependencies": dependencies_config} if dependencies_config else {}
