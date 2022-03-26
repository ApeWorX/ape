import json
import shutil
import tempfile
from pathlib import Path
from typing import Dict, List, Optional, Type, Union

import yaml
from ethpm_types import Compiler, ContractType, PackageManifest
from ethpm_types.utils import compute_checksum

from ape.api.projects import DependencyAPI, ProjectAPI
from ape.contracts import ContractContainer
from ape.exceptions import ProjectError
from ape.logging import logger
from ape.utils import (
    ManagerAccessMixin,
    cached_property,
    get_all_files_in_directory,
    get_relative_path,
    github_client,
)

from .base import BaseManager
from .config import CONFIG_FILE_NAME


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

        for extension in self.compiler_manager.registered_compilers:
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
            if self.contracts_folder.name != "contracts":
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
        sources = {s for s in self.sources if s in file_paths} if file_paths else set(self.sources)

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
        with self.config_manager.using_project(self.path, contracts_folder=self.contracts_folder):
            compiled_contract_types = self.compiler_manager.compile(needs_compiling)
            contract_types.update(compiled_contract_types)

            # NOTE: Update contract types & re-calculate source code entries in manifest
            sources = (
                {s for s in self.sources if s in file_paths} if file_paths else set(self.sources)
            )

            dependencies = {c for c in get_all_files_in_directory(self.contracts_folder / ".cache")}
            for contract in dependencies:
                sources.add(contract)

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
    _cached_dependencies: Dict[str, Dict[str, DependencyAPI]] = {}

    def __init__(
        self,
        path: Path,
    ) -> None:
        self.path = Path(path) if isinstance(path, str) else path

    def __str__(self) -> str:
        return f'Project("{self.path}")'

    @property
    def dependencies(self) -> Dict[str, DependencyAPI]:
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

    def __getattr__(self, attr_name: str) -> ContractContainer:
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

        if not self.contracts_folder.exists():
            return {}

        in_source_cache = self.contracts_folder / ".cache"
        if not use_cache and in_source_cache.exists():
            shutil.rmtree(str(in_source_cache))

        self._load_dependencies()
        file_paths = [file_paths] if isinstance(file_paths, Path) else file_paths

        manifest = self._project.create_manifest(file_paths, use_cache=use_cache)
        return manifest.contract_types or {}

    def _load_dependencies(self) -> Dict[str, DependencyAPI]:
        if self.path.name not in self._cached_dependencies:
            deps = {d.name: d for d in self.config_manager.dependencies}
            for api in deps.values():
                api.extract_manifest()  # Downloads if needed

            self._cached_dependencies[self.path.name] = deps

        return self._cached_dependencies[self.path.name]

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


class DependencyManager(ManagerAccessMixin):
    DATA_FOLDER: Path

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

        return dependency_classes  # type: ignore

    def decode_dependency(self, config_dependency_data: Dict) -> DependencyAPI:
        for key, dependency_cls in self.dependency_types.items():
            if key in config_dependency_data:
                return dependency_cls(
                    **config_dependency_data,
                )  # type: ignore

        dep_id = config_dependency_data.get("name", json.dumps(config_dependency_data))
        raise ProjectError(f"No installed dependency API that supports '{dep_id}'.")
