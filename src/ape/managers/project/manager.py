import shutil
from pathlib import Path
from typing import Dict, List, Optional, Type, Union

from ethpm_types import Compiler, ContractType, PackageManifest

from ape.api import DependencyAPI, ProjectAPI
from ape.contracts import ContractContainer, ContractNamespace
from ape.exceptions import ProjectError
from ape.managers.base import BaseManager
from ape.managers.project.types import ApeProject, BrownieProject


class ProjectManager(BaseManager):
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

    _cached_projects: Dict[str, ProjectAPI] = {}
    _cached_dependencies: Dict[str, Dict[str, Dict[str, DependencyAPI]]] = {}

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = Path(path) if isinstance(path, str) else path

    def __str__(self) -> str:
        return f'Project("{self.path}")'

    @property
    def dependencies(self) -> Dict[str, Dict[str, DependencyAPI]]:
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

        return self.config_manager.contracts_folder

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

        for extension in self.compiler_manager.registered_compilers:
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

    def extract_manifest(self) -> PackageManifest:
        """
        Extracts a package manifest from the project

        Returns:
            ethpm_types.manifest.PackageManifest
        """
        return self._project.create_manifest()

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

        for extension, compiler in self.compiler_manager.registered_compilers.items():
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

        project_classes.append(BrownieProject)
        project_classes.append(ApeProject)

        return project_classes

    @property
    def _project(self) -> ProjectAPI:
        if self.path.name not in self._cached_projects:
            self._cached_projects[self.path.name] = self.get_project(
                self.path, self.contracts_folder
            )

        return self._cached_projects[self.path.name]

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
        contracts_folder = contracts_folder or path / "contracts"

        def _try_create_project(proj_cls: Type[ProjectAPI]) -> Optional[ProjectAPI]:
            with self.config_manager.using_project(path, contracts_folder=contracts_folder):
                proj = proj_cls(
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

    def __getattr__(self, attr_name: str) -> Union[ContractContainer, ContractNamespace]:
        """
        Get a contract container from an existing contract type in
        the local project using ``.`` access.

        **NOTE**: To get a dependency contract, use
        :py:attr:`~ape.managers.project.ProjectManager.dependencies`.

        Usage example::

            from ape import project

            contract = project.MyContract

        Raises:
            AttributeError: When the given name is not a contract in the project.

        Args:
            attr_name (str): The name of the contract in the project.

        Returns:
            :class:`~ape.contracts.ContractContainer`
        """

        contract = self._get_contract(attr_name)

        if not contract:
            # Check if using namespacing.
            namespaced_contracts = [
                ct
                for ct in [
                    self._get_contract(ct.name)
                    for n, ct in self.contracts.items()
                    if ct.name and n.split(".")[0] == attr_name
                ]
                if ct
            ]
            if namespaced_contracts:
                return ContractNamespace(attr_name, namespaced_contracts)

            # Fixes anomaly when accessing non-ContractType attributes.
            # Returns normal attribute if exists. Raises 'AttributeError' otherwise.
            return self.__getattribute__(attr_name)  # type: ignore

        return contract

    def get_contract(self, contract_name: str) -> ContractContainer:
        """
        Get a contract container from an existing contract type in
        the local project by name.

        **NOTE**: To get a dependency contract, use
        :py:attr:`~ape.managers.project.ProjectManager.dependencies`.

        Raises:
            KeyError: When the given name is not a contract in the project.

        Args:
            contract_name (str): The name of the contract in the project.

        Returns:
            :class:`~ape.contracts.ContractContainer`
        """

        contract = self._get_contract(contract_name)
        if not contract:
            raise ValueError(f"No contract found with name '{contract_name}'.")

        return contract

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
            if not directory.is_dir():
                return

            for file in directory.iterdir():
                if file.is_dir():
                    _append_extensions_in_dir(file)
                elif (
                    file.suffix
                    and file.suffix not in extensions_found
                    and file.suffix not in self.compiler_manager.registered_compilers
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
            file_paths (Optional[Union[List[Path], Path]]):
              Provide one or more contract file-paths to load. If excluded,
              will load all the contracts.
            use_cache (Optional[bool]): Set to ``False`` to force a re-compile.
              Defaults to ``True``.

        Returns:
            Dict[str, ``ContractType``]: A dictionary of contract names to their
            types for each compiled contract.
        """

        self._load_dependencies()

        if not self.contracts_folder.exists():
            return {}

        in_source_cache = self.contracts_folder / ".cache"
        if not use_cache and in_source_cache.exists():
            shutil.rmtree(str(in_source_cache))

        file_paths = [file_paths] if isinstance(file_paths, Path) else file_paths
        manifest = self._project.create_manifest(file_paths, use_cache=use_cache)
        return manifest.contract_types or {}

    def _load_dependencies(self) -> Dict[str, Dict[str, DependencyAPI]]:
        if self.path.name in self._cached_dependencies:
            return self._cached_dependencies[self.path.name]

        dependencies: Dict[str, Dict[str, DependencyAPI]] = {}
        for dependency_config in self.config_manager.dependencies:
            dependency_config.extract_manifest()
            version_id = dependency_config.version_id
            if dependency_config.name in dependencies:
                dependencies[dependency_config.name][version_id] = dependency_config
            else:
                dependencies[dependency_config.name] = {version_id: dependency_config}

        self._cached_dependencies[self.path.name] = dependencies
        return dependencies

    def _get_contract(self, name: str) -> Optional[ContractContainer]:
        if name in self.contracts:
            return self.create_contract_container(
                contract_type=self.contracts[name],
            )

        return None

    # @property
    # def meta(self) -> PackageMeta:
    #     return PackageMeta(**self.config_manager.get_config("ethpm").serialize())

    # def publish_manifest(self):
    #     manifest = self.manifest.dict()
    #     if not manifest["name"]:
    #         raise ProjectError("Need name to release manifest")
    #     if not manifest["version"]:
    #         raise ProjectError("Need version to release manifest")
    #     TODO: Clean up manifest and minify it
    #     TODO: Publish sources to IPFS and replace with CIDs
    #     TODO: Publish to IPFS
