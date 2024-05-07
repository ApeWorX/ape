import os.path
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Sequence, Union

from ethpm_types import Checksum, Compiler, ContractType, PackageManifest, Source
from ethpm_types.source import Content
from packaging.version import InvalidVersion, Version
from pydantic import AnyUrl, ValidationError

from ape.exceptions import ProjectError
from ape.logging import logger
from ape.utils import (
    BaseInterfaceModel,
    ExtraAttributesMixin,
    ExtraModelAttributes,
    abstractmethod,
    cached_property,
    create_tempdir,
    get_all_files_in_directory,
    get_relative_path,
    log_instead_of_fail,
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

    @log_instead_of_fail(default="<ProjectAPI>")
    def __repr__(self) -> str:
        cls_name = getattr(type(self), "__name__", ProjectAPI.__name__)
        return f"<{cls_name} {self.path.name}>"

    @property
    @abstractmethod
    def is_valid(self) -> bool:
        """
        ``True`` if the project at the given path matches this project type.
        Useful for figuring out the best ``ProjectAPI`` to use when compiling a project.
        """

    @property
    def manifest(self) -> PackageManifest:
        return self.cached_manifest or PackageManifest()

    @abstractmethod
    def create_manifest(
        self, file_paths: Optional[Sequence[Path]] = None, use_cache: bool = True
    ) -> PackageManifest:
        """
        Create a manifest from the project.

        Args:
            file_paths (Optional[Sequence[Path]]): An optional list of paths to compile
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
            # Rely on individual cache files.
            self._contracts = manifest.contract_types
            manifest.contract_types = {}

        else:
            contracts: Dict[str, ContractType] = {}

            # Exclude contracts with missing sources, else you'll get validation errors.
            # This scenario happens if changing branches and you have some contracts on
            # one branch and others on the next.
            for name, contract in self.contracts.items():
                if (source_id := contract.source_id) and source_id in (manifest.sources or {}):
                    contracts[name] = contract

            manifest.contract_types = contracts

        return manifest

    @property
    def contracts(self) -> Dict[str, ContractType]:
        if contracts := self._contracts:
            return contracts

        contracts = {}
        for p in self._cache_folder.glob("*.json"):
            if p == self.manifest_cachefile:
                continue

            contract_name = p.stem
            contract_type = ContractType.model_validate_json(p.read_text())
            contract_type.name = contract_name if contract_type.name is None else contract_type.name
            contracts[contract_type.name] = contract_type

        self._contracts = contracts
        return self._contracts

    @property
    def _cache_folder(self) -> Path:
        folder = self.contracts_folder.parent / ".build"
        # NOTE: If we use the cache folder, we expect it to exist
        folder.mkdir(exist_ok=True, parents=True)
        return folder

    def update_manifest(self, **kwargs) -> PackageManifest:
        """
        Add additional package manifest parts to the cache.

        Args:
            **kwargs: Fields from ``ethpm_types.manifest.PackageManifest``.
        """
        new_manifest = self.manifest.model_copy(update=kwargs)
        return self.replace_manifest(new_manifest)

    def replace_manifest(self, manifest: PackageManifest) -> PackageManifest:
        """
        Replace the entire cached manifest.

        Args:
            manifest (``ethpm_types.manifest.PackageManifest``): The manifest
              to use.
        """
        self.manifest_cachefile.unlink(missing_ok=True)
        self.manifest_cachefile.write_text(manifest.model_dump_json())
        self._cached_manifest = manifest
        return manifest

    def process_config_file(self, **kwargs) -> bool:
        """
        Process the project's config file.
        Returns ``True`` if had to create a temporary ``ape-config.yaml`` file.
        """

        return False

    def add_compiler_data(self, compiler_data: Sequence[Compiler]) -> List[Compiler]:
        """
        Add compiler data to the existing cached manifest.

        Args:
            compiler_data (List[``ethpm_types.Compiler``]): Compilers to add.

        Returns:
            List[``ethpm_types.source.Compiler``]: The full list of compilers.
        """
        # Validate given data.
        given_compilers = set(compiler_data)
        if len(given_compilers) != len(compiler_data):
            raise ProjectError(
                f"`{self.add_compiler_data.__name__}()` was given multiple of the same compiler. "
                "Please filter inputs."
            )

        # Filter out given compilers without contract types.
        given_compilers = {c for c in given_compilers if c.contractTypes}
        if len(given_compilers) != len(compiler_data):
            logger.warning(
                f"`{self.add_compiler_data.__name__}()` given compilers without contract types. "
                "Ignoring these inputs."
            )

        for given_compiler in given_compilers:
            other_given_compilers = [c for c in given_compilers if c != given_compiler]
            contract_types_from_others = [
                n for c in other_given_compilers for n in (c.contractTypes or [])
            ]

            collisions = {
                n for n in (given_compiler.contractTypes or []) if n in contract_types_from_others
            }
            if collisions:
                collide_str = ", ".join(collisions)
                raise ProjectError(f"Contract type(s) '{collide_str}' collision across compilers.")

        new_types = [n for c in given_compilers for n in (c.contractTypes or [])]

        # Merge given compilers with existing compilers.
        existing_compilers = self.manifest.compilers or []

        # Existing compilers remaining after processing new compilers.
        remaining_existing_compilers: List[Compiler] = []

        for existing_compiler in existing_compilers:
            find_iter = iter(x for x in compiler_data if x == existing_compiler)

            if matching_given_compiler := next(find_iter, None):
                # Compiler already exists in the system, possibly with different contract types.
                # Merge contract types.
                matching_given_compiler.contractTypes = list(
                    {
                        *(existing_compiler.contractTypes or []),
                        *(matching_given_compiler.contractTypes or []),
                    }
                )
                # NOTE: Purposely we don't add the existing compiler back,
                #   as it is the same as the given compiler, (meaning same
                #   name, version, and settings), and we have
                #   merged their contract types.

                continue

            else:
                # Filter out contract types added now under a different compiler.
                existing_compiler.contractTypes = [
                    c for c in (existing_compiler.contractTypes or []) if c not in new_types
                ]

                # Remove compilers without contract types.
                if existing_compiler.contractTypes:
                    remaining_existing_compilers.append(existing_compiler)

        # Use Compiler.__hash__ to remove duplicated.
        # Also, sort for consistency.
        compilers = sorted(
            list({*remaining_existing_compilers, *compiler_data}),
            key=lambda x: f"{x.name}@{x.version}",
        )
        manifest = self.update_manifest(compilers=compilers)
        return manifest.compilers or compilers  # Or for mypy.

    def update_manifest_sources(
        self,
        source_paths: List[Path],
        contracts_path: Path,
        contract_types: Dict[str, ContractType],
        name: Optional[str] = None,
        version: Optional[str] = None,
        compiler_data: Optional[List[Compiler]] = None,
        **kwargs: Any,
    ) -> PackageManifest:
        items: Dict = {
            "contract_types": contract_types,
            "sources": self._create_source_dict(source_paths, contracts_path),
            "compilers": compiler_data or [],
        }
        if name is not None:
            items["name"] = name.lower()
        if version:
            items["version"] = version

        return self.update_manifest(**{**items, **kwargs})

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
                checksum=Checksum.from_file(source_path),
                urls=[],
                content=Content(root={i + 1: x for i, x in enumerate(text.splitlines())}),
                imports=source_imports.get(key, []),
                references=source_references.get(key, []),
            )

        return source_dict  # {source_id: Source}


class DependencyAPI(ExtraAttributesMixin, BaseInterfaceModel):
    """
    A base-class for dependency sources, such as GitHub or IPFS.
    """

    name: str
    """The name of the dependency."""

    version: Optional[str] = None
    """
    The version of the dependency. Omit to use the latest.
    """

    # TODO: Remove in 0.8.
    contracts_folder: str = "contracts"
    """
    The name of the dependency's ``contracts/`` directory.
    This is where ``ape`` will look for source files when compiling
    the manifest for this dependency.

    **Deprecated**: Use ``config_override:contracts_folder``.
    """

    # TODO: Remove in 0.8.
    exclude: List[str] = []
    """
    A list of glob-patterns for excluding files in dependency projects.
    **Deprecated**: Use ``config_override:compile:exclude``.
    """

    config_override: Dict = {}
    """
    Extra settings to include in the dependency's configuration.
    """

    _cached_manifest: Optional[PackageManifest] = None

    @log_instead_of_fail(default="<DependencyAPI>")
    def __repr__(self) -> str:
        cls_name = getattr(type(self), "__name__", DependencyAPI.__name__)
        return f"<{cls_name} name='{self.name}'>"

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        yield ExtraModelAttributes(
            name=self.name,
            attributes=lambda: self.contracts,
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

        with create_tempdir() as path:
            contracts_folder = path / config_data.get("contracts_folder", "contracts")

            if "contracts_folder" not in config_data:
                config_data["contracts_folder"] = contracts_folder

            with self.config_manager.using_project(path, **config_data) as project:
                manifest.unpack_sources(contracts_folder)
                compiled_manifest = project.local_project.create_manifest()

                if not compiled_manifest.contract_types:
                    # Manifest is empty. No need to write to disk.
                    logger.warning(
                        "Compiled manifest produced no contract types! "
                        "Are you missing compiler plugins?"
                    )
                    return compiled_manifest

                self.replace_manifest(compiled_manifest)
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
                manifest = PackageManifest.model_validate_json(project_path.read_text())
            except ValueError as err:
                if project_path.parent.is_dir():
                    project_path = project_path.parent
                else:
                    raise ProjectError(f"Invalid manifest file: '{project_path}'.") from err

            else:
                # Was given a path to a manifest JSON.
                self.replace_manifest(manifest)
                return manifest

        elif (project_path.parent / project_path.name.replace("-", "_")).is_dir():
            project_path = project_path.parent / project_path.name.replace("-", "_")

        elif (project_path.parent / project_path.name.replace("_", "-")).is_dir():
            project_path = project_path.parent / project_path.name.replace("_", "-")

        elif project_path.parent.is_dir():
            project_path = project_path.parent

        # TODO: In 0.8, delete self.contracts_folder and rely on cfg override.
        contracts_folder = self.config_override.get("contracts_folder", self.contracts_folder)

        # NOTE: Dependencies are not compiled here. Instead, the sources are packaged
        # for later usage via imports. For legacy reasons, many dependency-esque projects
        # are not meant to compile on their own.

        with self.config_manager.using_project(
            project_path,
            contracts_folder=(project_path / contracts_folder).expanduser().resolve(),
        ) as pm:
            project = pm.local_project
            if sources := self._get_sources(project):
                dependencies = self.project_manager._extract_manifest_dependencies()

                extras: Dict = {}
                if dependencies:
                    extras["dependencies"] = dependencies

                project.update_manifest_sources(
                    sources,
                    project.contracts_folder,
                    {},
                    name=project.name,
                    version=project.version,
                    **extras,
                )
            else:
                raise ProjectError(
                    f"No source files found in dependency '{self.name}'. "
                    "Try adjusting its config using `config_override` to "
                    "get Ape to recognize the project. "
                    "\nMore information: https://docs.apeworx.io/ape/stable"
                    "/userguides/dependencies.html#config-override"
                )

        # Replace the dependency's manifest with the temp project's.
        self.replace_manifest(project.manifest)
        return project.manifest

    def _get_sources(self, project: ProjectAPI) -> List[Path]:
        escaped_extensions = [re.escape(ext) for ext in self.compiler_manager.registered_compilers]
        extension_pattern = "|".join(escaped_extensions)
        pattern = rf".*({extension_pattern})"
        all_sources = get_all_files_in_directory(project.contracts_folder, pattern=pattern)

        # TODO: In 0.8, delete self.exclude and only use config override.
        exclude = [
            *(self.exclude or []),
            *(self.config_override.get("compile", {}).get("exclude", []) or []),
        ]

        excluded_files = set()
        for pattern in set(exclude):
            excluded_files.update({f for f in project.contracts_folder.glob(pattern)})

        return [s for s in all_sources if s not in excluded_files]

    def replace_manifest(self, manifest: PackageManifest):
        self._target_manifest_cache_file.unlink(missing_ok=True)
        self._target_manifest_cache_file.parent.mkdir(exist_ok=True, parents=True)
        self._target_manifest_cache_file.write_text(manifest.model_dump_json())
        self._cached_manifest = manifest


def _load_manifest_from_file(file_path: Path) -> Optional[PackageManifest]:
    if not file_path.is_file():
        return None

    try:
        return PackageManifest.model_validate_json(file_path.read_text())
    except ValidationError as err:
        logger.warning(
            f"Existing manifest file '{file_path}' corrupted (problem={err}). Re-building."
        )
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
