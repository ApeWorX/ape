import shutil
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Type, Union, cast

from ethpm_types import ContractInstance as EthPMContractInstance
from ethpm_types import ContractType, PackageManifest, PackageMeta, Source
from ethpm_types.contract_type import BIP122_URI
from ethpm_types.manifest import PackageName
from ethpm_types.source import Compiler, ContractSource
from ethpm_types.utils import AnyUrl, Hex

from ape.api import DependencyAPI, ProjectAPI
from ape.contracts import ContractContainer, ContractInstance, ContractNamespace
from ape.exceptions import ApeAttributeError, APINotImplementedError, ChainError, ProjectError
from ape.logging import logger
from ape.managers.base import BaseManager
from ape.managers.project.types import ApeProject, BrownieProject
from ape.utils import get_relative_path


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

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = Path(path) if isinstance(path, str) else path
        if self.path.is_file():
            self.path = self.path.parent

    def __str__(self) -> str:
        return f'Project("{self.path}")'

    @property
    def dependencies(self) -> Dict[str, Dict[str, DependencyAPI]]:
        """
        The package manifests of all dependencies mentioned
        in this project's ``ape-config.yaml`` file.
        """

        return self.load_dependencies()

    @property
    def sources(self) -> Dict[str, Source]:
        """
        A mapping of source identifier to ``ethpm_types.Source`` object.
        """

        return ProjectAPI._create_source_dict(self.source_paths, self.contracts_folder)

    # NOTE: Using these paths should handle the case when the folder doesn't exist
    @property
    def contracts_folder(self) -> Path:
        """
        The path to project's ``contracts/`` directory.

        Returns:
            pathlib.Path
        """

        folder = self.config_manager.contracts_folder
        if folder is None:
            # This happens when using normal Python REPL
            # and perhaps other times when loading a project before config.
            self.config_manager.load()
            folder = self.config_manager.contracts_folder
            if folder is None:
                # Was set explicitly to `None` in config.
                return self.path / "contracts"

        return folder

    @property
    def source_paths(self) -> List[Path]:
        """
        All the source files in the project.
        Excludes files with extensions that don't have a registered compiler.

        Returns:
            List[pathlib.Path]: A list of a source file paths in the project.
        """
        files: List[Path] = []
        if not self.contracts_folder.is_dir():
            return files

        for extension in self.compiler_manager.registered_compilers:
            files.extend((x for x in self.contracts_folder.rglob(f"*{extension}") if x.is_file()))

        return files

    @property
    def sources_missing(self) -> bool:
        """
        ``True`` when there are no contracts anywhere to be found
        in the project. ``False`` otherwise.
        """

        return not self.contracts_folder.is_dir() or not self.contracts_folder.iterdir()

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

    @property
    def compiler_data(self) -> List[Compiler]:
        """
        A list of ``Compiler`` objects representing the raw-data specifics of a compiler.
        """
        return self._get_compiler_data()

    def get_compiler_data(self, compile_if_needed: bool = True) -> List[Compiler]:
        """
        A list of ``Compiler`` objects representing the raw-data specifics of a compiler.

        Args:
            compile_if_needed (bool): Set to ``False`` to only return cached compiler data.
              Defaults to ``True``.

        Returns:
            List[Compiler]
        """
        return self._get_compiler_data(compile_if_needed=compile_if_needed)

    def _get_compiler_data(self, compile_if_needed: bool = True):
        contract_types: Iterable[ContractType] = (
            self.contracts.values()
            if compile_if_needed
            else self._get_cached_contract_types().values()
        )
        compiler_list: List[Compiler] = []
        contracts_folder = self.config_manager.contracts_folder
        for ext, compiler in self.compiler_manager.registered_compilers.items():
            sources = [x for x in self.source_paths if x.is_file() and x.suffix == ext]
            if not sources:
                continue

            try:
                version_map = compiler.get_version_map(sources, contracts_folder)
            except APINotImplementedError:
                versions = list(compiler.get_versions(sources))
                if len(versions) == 0:
                    # Skipping compilers that don't use versions
                    # These are unlikely to be part of the published manifest
                    continue
                elif len(versions) > 1:
                    raise (ProjectError(f"Unable to create version map for '{ext}'."))

                version = versions[0]
                version_map = {version: sources}

            settings = compiler.get_compiler_settings(sources, base_path=contracts_folder)
            for version, paths in version_map.items():
                version_settings = settings.get(version, {}) if version and settings else {}
                source_ids = [str(get_relative_path(p, contracts_folder)) for p in paths]
                filtered_contract_types = [
                    ct for ct in contract_types if ct.source_id in source_ids
                ]
                contract_type_names = [ct.name for ct in filtered_contract_types if ct.name]
                compiler_list.append(
                    Compiler(
                        name=compiler.name,
                        version=str(version),
                        settings=version_settings,
                        contractTypes=contract_type_names,
                    )
                )
        return compiler_list

    @property
    def meta(self) -> PackageMeta:
        """
        Metadata about the active project as per EIP
        https://eips.ethereum.org/EIPS/eip-2678#the-package-meta-object
        Use when publishing your package manifest.
        """

        return self.config_manager.meta

    @property
    def tracked_deployments(self) -> Dict[BIP122_URI, Dict[str, EthPMContractInstance]]:
        """
        Deployments that have been explicitly tracked via
        :meth:`~ape.managers.project.manager.ProjectManager.track_deployment`.
        These deployments will be included in the final package manifest upon publication
        of this package.
        """

        deployments: Dict[BIP122_URI, Dict[str, EthPMContractInstance]] = {}
        if not self._package_deployments_folder.is_dir():
            return deployments

        for ecosystem_path in [x for x in self._package_deployments_folder.iterdir() if x.is_dir()]:
            for deployment_path in [x for x in ecosystem_path.iterdir() if x.suffix == ".json"]:
                ethpm_instance = EthPMContractInstance.parse_file(deployment_path)
                if not ethpm_instance:
                    continue

                uri = BIP122_URI(f"blockchain://{ecosystem_path.name}/block/{ethpm_instance.block}")
                deployments[uri] = {deployment_path.stem: ethpm_instance}

        return deployments

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
    def local_project(self) -> ProjectAPI:
        return self.get_project(self.path, contracts_folder=self.contracts_folder)

    def extract_manifest(self) -> PackageManifest:
        """
        Extracts a package manifest from the project.

        Returns:
            ethpm_types.manifest.PackageManifest
        """
        manifest = self.local_project.create_manifest()
        manifest.meta = self.meta
        manifest.compilers = self.compiler_data
        manifest.deployments = self.tracked_deployments
        manifest.dependencies = self._extract_manifest_dependencies()
        return manifest

    def _extract_manifest_dependencies(self) -> Optional[Dict[PackageName, AnyUrl]]:
        package_dependencies: Dict[str, AnyUrl] = {}
        for dependency_config in self.config_manager.dependencies:
            package_name = dependency_config.name.replace("_", "-").lower()
            package_dependencies[package_name] = dependency_config.uri

        return cast(Optional[Dict[PackageName, AnyUrl]], package_dependencies)

    @property
    def _package_deployments_folder(self) -> Path:
        return self.local_project._cache_folder / "deployments"

    @property
    def _contract_sources(self) -> List[ContractSource]:
        sources = []
        for contract in self.contracts.values():
            contract_src = self._create_contract_source(contract)
            if contract_src:
                sources.append(contract_src)

        return sources

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

        if path.name in self._cached_projects:
            cached_project = self._cached_projects[path.name]
            if (
                version == cached_project.version
                and contracts_folder is not None
                and contracts_folder == cached_project.contracts_folder
            ):
                return cached_project

        contracts_folder = (
            (path / contracts_folder).expanduser().resolve()
            if contracts_folder
            else path / "contracts"
        )
        if not contracts_folder.is_dir():
            extensions = list(self.compiler_manager.registered_compilers.keys())
            path_patterns_to_ignore = self.config_manager.compiler.ignore_files

            def find_contracts_folder(sub_dir: Path) -> Optional[Path]:
                # Check if config file exists
                files_to_ignore = []
                for pattern in path_patterns_to_ignore:
                    files_to_ignore.extend(list(sub_dir.glob(pattern)))

                next_subs = []
                for sub in sub_dir.iterdir():
                    if sub.name.startswith("."):
                        continue

                    if sub.is_file() and sub not in files_to_ignore:
                        if sub.suffix in extensions:
                            return sub.parent

                    elif sub.is_dir():
                        next_subs.append(sub)

                # No source was found. Search next level of dirs.
                for next_sub in next_subs:
                    found = find_contracts_folder(next_sub)
                    if found:
                        return found

                return None

            contracts_folder = find_contracts_folder(path) or contracts_folder

        def _try_create_project(proj_cls: Type[ProjectAPI]) -> Optional[ProjectAPI]:
            with self.config_manager.using_project(
                path, contracts_folder=contracts_folder
            ) as _project:
                proj = proj_cls(
                    contracts_folder=_project.contracts_folder,
                    name=name,
                    path=path,
                    version=version,
                )
                if proj.is_valid:
                    return proj

            return None

        project_plugin_types = [pt for pt in self.project_types if not issubclass(pt, ApeProject)]
        for project_cls in project_plugin_types:
            project = _try_create_project(project_cls)
            if project:
                self._cached_projects[path.name] = project
                return project

        # Try 'ApeProject' last, in case there was a more specific one earlier.
        ape_project = _try_create_project(ApeProject)
        if ape_project:
            self._cached_projects[path.name] = ape_project
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
        if self.local_project.cached_manifest is None:
            return self.load_contracts()

        return self.local_project.contracts

    def __getattr__(self, attr_name: str) -> Any:
        """
        Get a contract container from an existing contract type in
        the local project using ``.`` access.

        **NOTE**: To get a dependency contract, use
        :py:attr:`~ape.managers.project.ProjectManager.dependencies`.

        Usage example::

            from ape import project

            contract = project.MyContract

        Raises:
            :class:`~ape.exceptions.ApeAttributeError`: When the given name is not
              a contract in the project.

        Args:
            attr_name (str): The name of the contract in the project.

        Returns:
            :class:`~ape.contracts.ContractContainer`,
            a :class:`~ape.contracts.ContractNamespace`, or any attribute.
        """

        result = self._get_attr(attr_name)
        if result:
            return result

        # Contract not found. Seek and re-compile missing contract types from sources.
        # This assists when build artifacts accidentally get deleted.
        all_source_ids = list(self.project_manager.sources.keys())
        compiled_source_ids = [x.source_id for x in self.contracts.values()]
        missing_sources = [
            self.contracts_folder / x for x in all_source_ids if x not in compiled_source_ids
        ]
        contract_types = self.compiler_manager.compile(missing_sources)

        # Cache all contract types that were missing for next time.
        for ct in contract_types.values():
            if not ct.name:
                continue

            # We know if we get here that the path does not exist.
            path = self.local_project._cache_folder / f"{ct.name}.json"
            path.write_text(ct.json())
            if self.local_project._contracts is None:
                self.local_project._contracts = {ct.name: ct}
            else:
                self.local_project._contracts[ct.name] = ct

        contract_type = contract_types.get(attr_name)
        if not contract_type:
            # Still not found. Contract likely doesn't exist.
            return self._handle_attr_or_contract_not_found(attr_name)

        result = self._get_attr(attr_name)
        if not result:
            # Shouldn't happen.
            return self._handle_attr_or_contract_not_found(attr_name)

        return result

    def _get_attr(self, attr_name: str):
        # Fixes anomaly when accessing non-ContractType attributes.
        # Returns normal attribute if exists. Raises 'AttributeError' otherwise.
        try:
            return self.__getattribute__(attr_name)
        except AttributeError:
            # Check if a contract.
            pass

        try:
            # NOTE: Will compile project (if needed)
            if contract := self._get_contract(attr_name):
                return contract

            # Check if using namespacing.
            namespaced_contracts = [
                ct
                for ct in [
                    self._get_contract(ct.name)
                    for n, ct in self.contracts.items()
                    if ct.name and "." in n and n.split(".")[0] == attr_name
                ]
                if ct
            ]
            if namespaced_contracts:
                return ContractNamespace(attr_name, namespaced_contracts)

        except Exception as err:
            # __getattr__ has to raise `AttributeError`
            raise ApeAttributeError(str(err)) from err

        return None

    def _handle_attr_or_contract_not_found(self, attr_name: str):
        message = f"{self.__class__.__name__} has no attribute or contract named '{attr_name}'."

        file_check_appended = False
        for file in self.contracts_folder.glob("**/*"):
            # Possibly, the user was trying to use a source ID instead of a contract name.
            if file.stem != attr_name:
                continue

            message = (
                f"{message} However, there is a source file named '{attr_name}', "
                "did you mean to reference a contract name from this source file?"
            )
            file_check_appended = True
            break

        # Possibly, the user does not have compiler plugins installed or working.
        missing_exts = self.extensions_with_missing_compilers([])
        if missing_exts:
            start = "Else, could" if file_check_appended else "Could"
            message = (
                f"{message} {start} it be from one of the missing compilers for extensions: "
                + f'{", ".join(sorted(missing_exts))}?'
            )

        raise ApeAttributeError(message)

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

        if contract := self._get_contract(contract_name):
            return contract

        raise ProjectError(f"No contract found with name '{contract_name}'.")

    def extensions_with_missing_compilers(
        self, extensions: Optional[List[str]] = None
    ) -> List[str]:
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

    def lookup_path(self, key_contract_path: Union[Path, str]) -> Optional[Path]:
        """
        Figure out the full path of the contract from the given ``key_contract_path``.

        For example, give it ``HelloWorld`` and it returns
        ``<absolute-project-path>/<contracts-folder>/HelloWorld.sol``.

        Another example is to give it ``contracts/HelloWorld.sol`` and it also
        returns ``<absolute-project-path>/<contracts-folder>/HelloWorld.sol``.

        Args:
            key_contract_path (pathlib.Path, str): A sub-path to a contract or a source ID.

        Returns:
            pathlib.Path: The path if it exists, else ``None``.
        """

        path = Path(key_contract_path)
        ext = path.suffix or None

        def find_in_dir(dir_path: Path) -> Optional[Path]:
            if not dir_path.is_dir():
                return None

            for file_path in dir_path.iterdir():
                if file_path.is_dir() and (result := find_in_dir(file_path)):
                    return result

                # If the user provided an extension, it has to match.
                ext_okay = ext == file_path.suffix if ext is not None else True

                # File found
                if file_path.stem == path.stem and ext_okay:
                    return file_path

            return None

        return find_in_dir(self.contracts_folder)

    def load_contracts(
        self, file_paths: Optional[Union[Iterable[Path], Path]] = None, use_cache: bool = True
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

        in_source_cache = self.contracts_folder / ".cache"
        if not use_cache and in_source_cache.is_dir():
            shutil.rmtree(str(in_source_cache))

        if isinstance(file_paths, Path):
            file_path_list = [file_paths]
        elif file_paths is not None:
            file_path_list = list(file_paths)
        else:
            file_path_list = None

        manifest = self.local_project.create_manifest(
            file_paths=file_path_list, use_cache=use_cache
        )
        return manifest.contract_types or {}

    def _get_cached_contract_types(self) -> Dict[str, ContractType]:
        if not self.local_project.cached_manifest:
            return {}

        return self.local_project.cached_manifest.contract_types or {}

    def load_dependencies(self, use_cache: bool = True) -> Dict[str, Dict[str, DependencyAPI]]:
        return self.dependency_manager.load_dependencies(self.path.as_posix(), use_cache=use_cache)

    def remove_dependency(self, dependency_name: str, versions: Optional[List[str]] = None):
        self.dependency_manager.remove_dependency(
            self.path.as_posix(), dependency_name, versions=versions
        )

    def track_deployment(self, contract: ContractInstance):
        """
        Indicate that a contract deployment should be included in the package manifest
        upon publication.

        **NOTE**: Deployments are automatically tracked for contracts. However, only
        deployments passed to this method are included in the final, publishable manifest.

        Args:
            contract (:class:`~ape.contracts.base.ContractInstance`): The contract
              to track as a deployment of the project.
        """

        if self.provider.network.is_dev:
            raise ProjectError("Can only publish deployments on a live network.")

        if not (contract_name := contract.contract_type.name):
            raise ProjectError("Contract name required when publishing.")

        try:
            receipt = contract.receipt
        except ChainError as err:
            raise ProjectError(
                f"Contract '{contract_name}' transaction receipt is unknown."
            ) from err

        block_number = receipt.block_number
        block_hash_bytes = self.provider.get_block(block_number).hash
        if not block_hash_bytes:
            # Mostly for mypy, not sure this can ever happen.
            raise ProjectError(
                f"Block hash containing transaction for '{contract_name}' "
                f"at block_number={block_number} is unknown."
            )

        block_hash = block_hash_bytes.hex()
        artifact = EthPMContractInstance(
            address=cast(Hex, contract.address),
            block=block_hash,
            contractType=contract_name,
            transaction=cast(Hex, contract.txn_hash),
            runtimeBytecode=contract.contract_type.runtime_bytecode,
        )

        block_0_hash = self.provider.get_block(0).hash
        if not block_0_hash:
            raise ProjectError("Chain missing hash for block 0 (required for BIP-122 chain ID).")

        bip122_chain_id = block_0_hash.hex()
        deployments_folder = self._package_deployments_folder / bip122_chain_id
        deployments_folder.mkdir(exist_ok=True, parents=True)
        destination = deployments_folder / f"{contract_name}.json"

        if destination.is_file():
            logger.debug("Deployment already tracked. Re-tracking.")
            # NOTE: missing_ok=True to handle race condition.
            destination.unlink(missing_ok=True)

        destination.write_text(artifact.json())

    def _create_contract_source(self, contract_type: ContractType) -> Optional[ContractSource]:
        if not (source_id := contract_type.source_id):
            return None

        if not (src := self._lookup_source(source_id)):
            return None

        try:
            return ContractSource.create(contract_type, src, self.contracts_folder)
        except (ValueError, FileNotFoundError):
            return None

    def _lookup_source(self, source_id: str) -> Optional[Source]:
        source_path = self.lookup_path(source_id)
        if source_path and source_path.is_file():
            result = self.local_project._create_source_dict(source_path, self.contracts_folder)
            return next(iter(result.values())) if result else None

        return None

    def _get_contract(self, name: str) -> Optional[ContractContainer]:
        # NOTE: Use `load_contracts()` to re-compile changed contracts if needed.
        #   Else, if you make changes to a contract, it won't catch the need to re-compile.
        if name in self.load_contracts():
            return self.chain_manager.contracts.get_container(self.contracts[name])

        return None

    # def publish_manifest(self):
    #     manifest = self.manifest.dict()
    #     if not manifest["name"]:
    #         raise ProjectError("Need name to release manifest")
    #     if not manifest["version"]:
    #         raise ProjectError("Need version to release manifest")

    #     TODO: Publish sources to IPFS and replace with CIDs
    #     TODO: Publish to IPFS
