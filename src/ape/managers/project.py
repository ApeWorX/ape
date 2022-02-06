import json
import shutil
import sys
import tempfile
from importlib import import_module
from pathlib import Path
from typing import ClassVar, Dict, List, Optional, Type, Union

import yaml
from ethpm_types import Compiler, ContractType, PackageManifest
from ethpm_types.utils import compute_checksum

from ape.api.projects import DependencyAPI, ProjectAPI
from ape.contracts import ContractContainer
from ape.exceptions import ProjectError
from ape.logging import logger
from ape.plugins import PluginManager
from ape.utils import cached_property, get_relative_path, github_client, injected_before_use

from .compilers import CompilerManager
from .config import CONFIG_FILE_NAME, ConfigManager
from .converters import ConversionManager
from .networks import NetworkManager


class ApeProject(ProjectAPI):
    """
    The default implementation of the :class:`~ape.api.projects.ProjectAPI`.
    By default, the `:class:`~ape.managers.project.ProjectManager` uses an
    ``ApeProject`` at the current-working directory.
    """

    @property
    def is_valid(self) -> bool:
        if (self.path / CONFIG_FILE_NAME).exists():
            return True

        logger.warning(
            f"'{self.path.name}' is not an 'ApeProject', but attempting to process as one."
        )

        # NOTE: We always return True as a last-chance attempt because it often
        # works anyway and prevents unnecessary plugin requirements.
        return True

    @property
    def sources(self) -> List[Path]:
        """
        All the source files in the project.
        Excludes files with extensions that don't have a registered compiler.

        Returns:
            List[pathlib.Path]: A list of a source file paths in the project.
        """

        files: List[Path] = []
        if not self.contracts_folder.exists():
            return files

        for extension in self.compilers.registered_compilers:
            files.extend(self.contracts_folder.rglob(f"*{extension}"))

        return files

    def create_manifest(
        self, file_paths: Optional[List[Path]] = None, use_cache: bool = True
    ) -> PackageManifest:
        # Create a config file if one doesn't exist to forward values from
        # the root project's 'ape-config.yaml' 'dependencies:' config.
        config_file = self.path / CONFIG_FILE_NAME
        if not config_file.exists():
            config_data = {}
            if self.name:
                config_data["name"] = self.name
            if self.version:
                config_data["version"] = self.version
            if self.contracts_folder != "contracts":
                # Only sets when not default.
                config_data["contracts_folder"] = self.contracts_folder.name
            if config_data:
                with open(config_file, "w") as f:
                    yaml.safe_dump(config_data, f)

        # Load a cached or clean manifest (to use for caching)
        if self.cached_manifest and use_cache:
            manifest = self.cached_manifest
        else:
            manifest = PackageManifest()
            if self.manifest_cachefile.exists():
                self.manifest_cachefile.unlink()

        cached_sources = manifest.sources or {}
        cached_contract_types = manifest.contract_types or {}
        sources = {s for s in self.sources if s in file_paths} if file_paths else self.sources

        # Filter out deleted sources
        deleted_source_ids = cached_sources.keys() - set(
            map(str, [get_relative_path(s, self.contracts_folder) for s in sources])
        )
        contract_types = {
            name: contract_type
            for name, contract_type in cached_contract_types.items()
            if contract_type.source_id not in deleted_source_ids
        }

        def file_needs_compiling(source: Path) -> bool:
            path = str(get_relative_path(source, self.contracts_folder))

            if path not in cached_sources:
                return True  # New file added

            cached = cached_sources[path]
            cached.compute_checksum(algorithm="md5")
            assert cached.checksum  # For mypy

            source_file = self.contracts_folder / source
            checksum = compute_checksum(
                source_file.read_bytes(),
                algorithm=cached.checksum.algorithm,
            )

            return checksum != cached.checksum.hash  # Contents changed

        # NOTE: Filter by checksum to only update what's needed
        needs_compiling = list(filter(file_needs_compiling, sources))

        # Set the context in case compiling a dependency (or anything outside the root project).
        with self.compilers.config.using_project(self.path, contracts_folder=self.contracts_folder):
            self.compilers.config.PROJECT_FOLDER = self.path
            self.compilers.config.contracts_folder = self.contracts_folder
            compiled_contract_types = self.compilers.compile(needs_compiling)
            contract_types.update(compiled_contract_types)

            # NOTE: Update contract types & re-calculate source code entries in manifest
            sources = {s for s in self.sources if s in file_paths} if file_paths else self.sources
            manifest = self._create_manifest(
                sources,
                self.contracts_folder,
                contract_types,
                initial_manifest=manifest,
            )

            # NOTE: Cache the updated manifest to disk (so ``self.cached_manifest`` reads next time)
            self.manifest_cachefile.write_text(json.dumps(manifest.dict()))
            return manifest


class LocalDependency(DependencyAPI):
    """
    A dependency that is already downloaded on the local machine.

    Config example::

        dependencies:
          - name: Dependency
            local: path/to/dependency
    """

    local: str

    @property
    def path(self) -> Path:
        given_path = Path(self.local)
        if not given_path.exists():
            raise ProjectError(f"No project exists at path '{given_path}'.")

        return given_path

    @property
    def version_id(self) -> str:
        return "local"

    def extract_manifest(self) -> PackageManifest:
        return self._extract_local_manifest(self.path)


class GithubDependency(DependencyAPI):
    """
    A dependency from Github. Use the ``github`` key in your ``dependencies:``
    section of your ``ape-config.yaml`` file to declare a dependency from GitHub.

    Config example::

        dependencies:
          - name: OpenZeppelin
            github: OpenZeppelin/openzeppelin-contracts
            version: 4.4.0
    """

    github: str
    """
    The Github repo ID e.g. the organization name followed by the repo name,
    such as ``dapphub/erc20``.
    """

    branch: Optional[str] = None
    """
    The branch to use. **NOTE**: Will be ignored if given a version.
    """

    @property
    def version_id(self) -> str:
        if self.branch:
            return self.branch

        if self.version and self.version != "latest":
            return self.version

        latest_release = github_client.get_release(self.github, "latest")
        return latest_release.tag_name

    def __repr__(self):
        return f"<{self.__class__.__name__} github={self.github}>"

    def extract_manifest(self) -> PackageManifest:
        if self.cached_manifest:
            # Already downloaded
            return self.cached_manifest

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_project_path = (Path(temp_dir) / self.name).resolve()
            temp_project_path.mkdir(exist_ok=True, parents=True)

            if self.branch:
                github_client.clone_repo(self.github, temp_project_path, branch=self.branch)

            else:
                github_client.download_package(
                    self.github, self.version or "latest", temp_project_path
                )

            return self._extract_local_manifest(temp_project_path)


class ProjectManager:
    """
    A manager for accessing contract-types, dependencies, and other project resources.
    Additionally, compile contracts using the
    :meth:`~ape.managers.project.ProjectManager.load_contracts` method.

    Use ``ape.project`` to reference the current project and ``ape.Project`` to reference
    this class uninitialized.

    Raises:
        :class:`~ape.exceptions.ProjectError`: When the project's dependencies are invalid.

    Usage example::

        from ape import project  # "project" is the ProjectManager for the active project
        from ape import Project  # Is a ProjectManager

        # MyContractType (example) is contract type in the active project
        contract_type = project.MyContactType
    """

    path: Path
    """The project path."""

    config: ClassVar[ConfigManager] = injected_before_use()  # type: ignore
    """
    A reference to :class:`~ape.managers.config.ConfigManager`, which
    manages project and plugin configurations.
    """

    converter: ClassVar[ConversionManager] = injected_before_use()  # type: ignore
    """
    A reference to the conversion utilities in
    :class:`~ape.managers.converters.ConversionManager`.
    """

    compilers: ClassVar[CompilerManager] = injected_before_use()  # type: ignore
    """
    The group of compiler plugins for compiling source files. See
    :class:`~ape.managers.compilers.CompilerManager` for more information.
    Call method :meth:`~ape.managers.project.ProjectManager.load_contracts` in this class
    to more easily compile sources.
    """

    networks: ClassVar[NetworkManager] = injected_before_use()  # type: ignore
    """
    The manager of networks, :class:`~ape.managers.networks.NetworkManager`.
    To get the active provide, use
    :py:attr:`ape.managers.networks.NetworkManager.active_provider`.
    """

    plugin_manager: ClassVar[PluginManager] = injected_before_use()  # type: ignore

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = Path(path) if isinstance(path, str) else path

    def __str__(self) -> str:
        return f'Project("{self.path}")'

    @cached_property
    def dependencies(self) -> Dict[str, PackageManifest]:
        """
        The package manifests of all dependencies mentioned
        in this project's ``ape-config.yaml`` file.
        """

        return self._load_dependencies()

    # NOTE: Using these paths should handle the case when the folder doesn't exist
    @property
    def contracts_folder(self) -> Path:
        """
        The path to project's ``contracts/`` directory.

        Returns:
            pathlib.Path
        """

        return self.config.contracts_folder

    @property
    def sources(self) -> List[Path]:
        """
        All the source files in the project.
        Excludes files with extensions that don't have a registered compiler.

        Returns:
            List[pathlib.Path]: A list of a source file paths in the project.
        """
        files: List[Path] = []
        if not self.contracts_folder.exists():
            return files

        for extension in self.compilers.registered_compilers:
            files.extend(self.contracts_folder.rglob(f"*{extension}"))

        return files

    @property
    def sources_missing(self) -> bool:
        """
        ``True`` when there are no contracts anywhere to be found
        in the project. ``False`` otherwise.
        """

        return not self.contracts_folder.exists() or not self.contracts_folder.iterdir()

    @property
    def interfaces_folder(self) -> Path:
        """
        The path to the ``interfaces/`` directory of the project.

        Returns:
            pathlib.Path
        """

        return self.path / "interfaces"

    @property
    def scripts_folder(self) -> Path:
        """
        The path to the ``scripts/`` directory of the project.

        Returns:
            pathlib.Path
        """

        return self.path / "scripts"

    @property
    def tests_folder(self) -> Path:
        """
        The path to the ``tests/`` directory of the project.

        Returns:
            pathlib.Path
        """

        return self.path / "tests"

    # TODO: Make this work for generating and caching the manifest file
    @property
    def compiler_data(self) -> List[Compiler]:
        """
        A list of objects representing the raw-data specifics of a compiler.

        Returns:
            List[``Compiler``]
        """

        compilers = []

        for extension, compiler in self.compilers.registered_compilers.items():
            for version in compiler.get_versions(
                [p for p in self.sources if p.suffix == extension]
            ):
                compilers.append(Compiler(compiler.name, version))  # type: ignore

        return compilers

    @property
    def project_types(self) -> List[Type[ProjectAPI]]:
        """
        The available :class:`~ape.api.project.ProjectAPI` types available,
        such as :class:`~ape.managers.project.ApeProject`, which is the default.
        """

        project_classes = []
        for _, (project_class,) in self.plugin_manager.projects:
            project_classes.append(project_class)

        project_classes.append(ApeProject)
        return project_classes

    @cached_property
    def _project(self) -> ProjectAPI:
        return self.get_project(self.path, self.contracts_folder)

    def get_project(
        self,
        path: Path,
        contracts_folder: Optional[Path] = None,
        name: Optional[str] = None,
        version: Optional[str] = None,
    ) -> ProjectAPI:
        """
        Get the project at the given path.
        Returns the first :class:`~ape.api.projects.ProjectAPI` it finds where it
        is valid.

        Args:
            path (pathlib.Path): The path to the project.
            contracts_folder (pathlib.Path): The path to the contracts folder. Defaults
              to ``<path>/contracts``.
            name (str): The name of the project. Only necessary when this project is
              a dependency. Defaults to ``None``.
            version (str): The project's version. Only necessary when this project is
              a dependency. Defaults to ``None``.

        Returns:
            :class:`~ape.api.projects.ProjectAPI`
        """

        def _try_create_project(proj_cls: Type[ProjectAPI]) -> Optional[ProjectAPI]:
            with self.config.using_project(
                path, contracts_folder=contracts_folder
            ) as project_manager:
                proj = proj_cls(
                    compilers=project_manager.compilers,
                    contracts_folder=contracts_folder,
                    name=name,
                    path=path,
                    version=version,
                )  # type: ignore
                if proj.is_valid:
                    return proj

            return None

        project_plugin_types = [pt for pt in self.project_types if not issubclass(pt, ApeProject)]
        for project_cls in project_plugin_types:
            project = _try_create_project(project_cls)
            if project:
                return project

        # Try 'ApeProject' last, in case there was a more specific one earlier.
        ape_project = _try_create_project(ApeProject)

        if ape_project:
            return ape_project

        raise ProjectError(f"'{self.path.name}' is not recognized as a project.")

    @property
    def contracts(self) -> Dict[str, ContractType]:
        """
        A dictionary of contract names to their type.
        See :meth:`~ape.managers.project.ProjectManager.load_contracts` for more information.

        Returns:
            Dict[str, ``ContractType``]
        """

        return self.load_contracts()

    def __getattr__(self, attr_name: str) -> ContractContainer:
        """
        Get a contract container from an existing contract type or dependency
        name using ``.`` access.

        Usage example::

            from ape import project

            contract = project.MyContract

        Args:
            attr_name (str): The name of the contract or dependency.

        Returns:
            :class:`~ape.contracts.ContractContainer`
        """

        contracts = self.load_contracts()
        if attr_name in contracts:
            contract_type = contracts[attr_name]
        elif attr_name in self.dependencies:
            contract_type = self.dependencies[attr_name]  # type: ignore
        else:
            # Fixes anomaly when accessing non-ContractType attributes.
            # Returns normal attribute if exists. Raises 'AttributeError' otherwise.
            return self.__getattribute__(attr_name)  # type: ignore

        return ContractContainer(  # type: ignore
            contract_type=contract_type,
            _provider=self.networks.active_provider,
            _converter=self.converter,
        )

    def extensions_with_missing_compilers(self, extensions: Optional[List[str]]) -> List[str]:
        """
        All file extensions in the ``contracts/`` directory (recursively)
        that do not correspond to a registered compiler.

        Args:
            extensions (List[str], optional): If provided, returns only extensions that
                are in this list. Useful for checking against a subset of source files.

        Returns:
            List[str]: A list of file extensions found in the ``contracts/`` directory
            that do not have associated compilers installed.
        """
        extensions_found = []

        def _append_extensions_in_dir(directory: Path):
            for file in directory.iterdir():
                if file.is_dir():
                    _append_extensions_in_dir(file)
                elif (
                    file.suffix
                    and file.suffix not in extensions_found
                    and file.suffix not in self.compilers.registered_compilers
                ):
                    extensions_found.append(file.suffix)

        _append_extensions_in_dir(self.contracts_folder)
        if extensions:
            extensions_found = [e for e in extensions_found if e in extensions]

        return extensions_found

    def lookup_path(self, key_contract_path: Path) -> Optional[Path]:
        """
        Figure out the full path of the contract from the given ``key_contract_path``.

        For example, give it ``HelloWorld`` and it returns
        ``<absolute-project-path>/<contracts-folder>/HelloWorld.sol``.

        Another example is to give it ``contracts/HelloWorld.sol`` and it also
        returns ``<absolute-project-path>/<contracts-folder>/HelloWorld.sol``.

        Args:
            key_contract_path (pathlib.Path): A sub-path to a contract.

        Returns:
            pathlib.Path: The path if it exists, else ``None``.
        """

        ext = key_contract_path.suffix or None

        def find_in_dir(dir_path: Path) -> Optional[Path]:
            for file_path in dir_path.iterdir():
                if file_path.is_dir():
                    result = find_in_dir(file_path)
                    if result:
                        return result

                # If the user provided an extension, it has to match.
                ext_okay = ext == file_path.suffix if ext is not None else True

                # File found
                if file_path.stem == key_contract_path.stem and ext_okay:
                    return file_path

            return None

        return find_in_dir(self.contracts_folder)

    def load_contracts(
        self, file_paths: Optional[Union[List[Path], Path]] = None, use_cache: bool = True
    ) -> Dict[str, ContractType]:
        """
        Compile and get the contract types in the project.
        This is called when invoking the CLI command ``ape compile`` as well as prior to running
        scripts or tests in ``ape``, such as from ``ape run`` or ``ape test``.

        Args:
            file_paths (List[pathlib.Path] or pathlib.Path], optional):
              Provide one or more contract file-paths to load. If excluded,
              will load all the contracts.
            use_cache (bool, optional): Set to ``False`` to force a re-compile.
              Defaults to ``True``.

        Returns:
            Dict[str, ``ContractType``]: A dictionary of contract names to their
            types for each compiled contract.
        """

        if not self.contracts_folder.exists():
            return {}

        self._load_dependencies()
        file_paths = [file_paths] if isinstance(file_paths, Path) else file_paths

        in_source_cache = self.contracts_folder / ".cache"
        if not use_cache and in_source_cache.exists():
            shutil.rmtree(str(in_source_cache))

        manifest = self._project.create_manifest(file_paths, use_cache=use_cache)
        return manifest.contract_types or {}

    def run_script(self, name: str, interactive: bool = False):
        """
        Run a script from the project :py:attr:`~ape.mangers.project.ProjectManager.scripts_folder`
        directory.

        Args:
            name (str): The script name.
            interactive (bool): Whether to launch the console as well. Defaults to ``False``.
        """

        available_scripts = {p.stem: p.resolve() for p in self.scripts_folder.glob("*.py")}

        if Path(name).exists():
            script_file = Path(name).resolve()

        elif not self.scripts_folder.exists():
            raise ProjectError("No 'scripts/' directory detected to run script.")

        elif name not in available_scripts:
            raise ProjectError(f"No script named '{name}' detected in scripts folder.")

        else:
            script_file = self.scripts_folder / name

        script_path = get_relative_path(script_file, Path.cwd())
        script_parts = script_path.parts[:-1]

        if any(p == ".." for p in script_parts):
            raise ProjectError("Cannot execute script from outside current directory")

        # Add to Python path so we can search for the given script to import
        root_path = Path(".").resolve().root
        sys.path.append(root_path)

        # Load the python module to find our hook functions
        try:
            import_str = ".".join(self.scripts_folder.resolve().parts[1:] + (script_path.stem,))
            py_module = import_module(import_str)
        except Exception as err:
            logger.error_from_exception(err, f"Exception while executing script: {script_path}")
            sys.exit(1)

        finally:
            # Undo adding the path to make sure it's not permanent
            sys.path.remove(root_path)

        # Execute the hooks
        if hasattr(py_module, "cli"):
            # TODO: Pass context to ``cli`` before calling it
            py_module.cli()  # type: ignore

        elif hasattr(py_module, "main"):
            # NOTE: ``main()`` accepts no arguments
            py_module.main()  # type: ignore

        else:
            raise ProjectError("No `main` or `cli` method detected")

        if interactive:
            from ape_console._cli import console

            return console()

    def _load_dependencies(self) -> Dict[str, PackageManifest]:
        return {d.name: d.extract_manifest() for d in self.config.dependencies}

    # @property
    # def meta(self) -> PackageMeta:
    #     return PackageMeta(**self.config.get_config("ethpm").serialize())

    # def publish_manifest(self):
    #     manifest = self.manifest.dict()
    #     if not manifest["name"]:
    #         raise ProjectError("Need name to release manifest")
    #     if not manifest["version"]:
    #         raise ProjectError("Need version to release manifest")
    #     TODO: Clean up manifest and minify it
    #     TODO: Publish sources to IPFS and replace with CIDs
    #     TODO: Publish to IPFS


class _DependencyManager:
    DATA_FOLDER: Path

    plugin_manager: ClassVar[PluginManager] = injected_before_use()  # type: ignore
    project_manager: ClassVar[ProjectManager] = injected_before_use()  # type: ignore

    def __init__(self, data_folder: Path):
        self.DATA_FOLDER = data_folder

    @cached_property
    def dependency_types(self) -> Dict[str, Type[DependencyAPI]]:
        dependency_classes = {
            "github": GithubDependency,
            "local": LocalDependency,
        }

        for _, (config_key, dependency_class) in self.plugin_manager.dependencies:
            dependency_classes[config_key] = dependency_class

        dependency_classes["github"] = GithubDependency
        dependency_classes["local"] = LocalDependency
        return dependency_classes

    def decode_dependency(self, config_dependency_data: Dict) -> DependencyAPI:
        for key, dependency_cls in self.dependency_types.items():
            if key in config_dependency_data:
                return dependency_cls(
                    **config_dependency_data,
                    project_manager=self.project_manager,
                    _data_folder=self.DATA_FOLDER,
                )  # type: ignore

        dep_id = config_dependency_data.get("name", json.dumps(config_dependency_data))
        raise ProjectError(f"No installed dependency API that supports '{dep_id}'.")
