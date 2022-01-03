import json
from pathlib import Path
from typing import Collection, Dict, List, Optional, Union

import requests
from dataclassy import dataclass

from ape.contracts import ContractContainer
from ape.exceptions import ProjectError
from ape.managers.networks import NetworkManager
from ape.types import Checksum, Compiler, ContractType, PackageManifest, Source
from ape.utils import compute_checksum, get_all_files_in_directory, github_client

from .compilers import CompilerManager
from .config import ConfigManager
from .converters import ConversionManager


def _create_source_dict(contracts_paths: Collection[Path]) -> Dict[str, Source]:
    return {
        str(source): Source(  # type: ignore
            checksum=Checksum(  # type: ignore
                algorithm="md5", hash=compute_checksum(source.read_bytes())
            ),
            urls=[],
        )
        for source in contracts_paths
    }


@dataclass
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
    config: ConfigManager
    converter: ConversionManager
    compilers: CompilerManager
    networks: NetworkManager

    dependencies: Dict[str, PackageManifest] = dict()

    def __post_init__(self):
        if isinstance(self.path, str):
            self.path = Path(self.path)

        self.dependencies = {
            n: self._extract_manifest(n, dep_id) for n, dep_id in self.config.dependencies.items()
        }

    def __repr__(self):
        return "<ProjectManager>"

    def _extract_manifest(self, name: str, download_path: str) -> PackageManifest:
        packages_path = self.config.DATA_FOLDER / "packages"
        packages_path.mkdir(exist_ok=True, parents=True)
        target_path = packages_path / name
        target_path.mkdir(exist_ok=True, parents=True)

        if download_path.startswith("https://") or download_path.startswith("http://"):
            manifest_file_path = target_path / "manifest.json"
            if manifest_file_path.exists():
                manifest_dict = json.loads(manifest_file_path.read_text())
            else:
                # Download manifest
                response = requests.get(download_path)
                manifest_file_path.write_text(response.text)
                manifest_dict = response.json()

            if "name" not in manifest_dict:
                raise ProjectError("Dependencies must have a name.")

            return PackageManifest.from_dict(manifest_dict)
        else:
            # Github dependency (format: <org>/<repo>@<version>)
            try:
                path, version = download_path.split("@")
            except ValueError:
                raise ValueError("Invalid Github ID. Must be given as <org>/<repo>@<version>")

            package_contracts_path = target_path / "contracts"
            is_cached = len([p for p in target_path.iterdir()]) > 0

            if not is_cached:
                github_client.download_package(path, version, target_path)

            if not package_contracts_path.exists():
                raise ProjectError(
                    "Dependency does not have a supported file structure. "
                    "Expecting 'contracts/' path."
                )

            manifest = PackageManifest()
            sources = [
                s
                for s in get_all_files_in_directory(package_contracts_path)
                if s.name not in ("package.json", "package-lock.json")
                and s.suffix in self.compilers.registered_compilers
            ]
            manifest.sources = _create_source_dict(sources)
            manifest.contractTypes = self.compilers.compile(sources)
            return manifest

    def __str__(self) -> str:
        return f'Project("{self.path}")'

    @property
    def _cache_folder(self) -> Path:
        folder = self.path / ".build"
        # NOTE: If we use the cache folder, we expect it to exist
        folder.mkdir(exist_ok=True)
        return folder

    @property
    def manifest_cachefile(self) -> Path:
        """
        The path to the project's cached manifest. The manifest
        is a cached file representing the project and is useful
        for sharing, such as uploading to IPFS.

        Returns:
            pathlib.Path
        """

        file_name = self.config.name or "__local__"
        return self._cache_folder / (file_name + ".json")

    @property
    def cached_manifest(self) -> Optional[PackageManifest]:
        """
        The cached :class:`~ape.types.manifest.PackageManifest`.
        If nothing has been compiled, then no manifest will exist, and
        this will return ``None``.
        """

        manifest_file = self.manifest_cachefile
        if manifest_file.exists():
            manifest_json = json.loads(manifest_file.read_text())
            if "manifest" not in manifest_json:
                raise ProjectError("Corrupted manifest.")

            return PackageManifest.from_dict(manifest_json)

        else:
            return None

    # NOTE: Using these paths should handle the case when the folder doesn't exist
    @property
    def contracts_folder(self) -> Path:
        """
        The path to project's ``contracts/`` directory.

        Returns:
            pathlib.Path
        """

        return self.path / "contracts"

    @property
    def sources(self) -> List[Path]:
        """
        All the source files in the project.
        Excludes files with extensions that don't have a registered compiler.

        Returns:
            List[pathlib.Path]: A list of a source file paths in the project.
        """
        files: List[Path] = []
        for extension in self.compilers.registered_compilers:
            files.extend(self.contracts_folder.rglob("*" + extension))

        return files

    @property
    def sources_missing(self) -> bool:
        """
        ``True`` when there are no contracts anywhere to be found
        in the project. ``False`` otherwise.
        """

        return not self.contracts_folder.exists() or not self.contracts_folder.iterdir()

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
        exts = []

        def _append_extensions_in_dir(directory: Path):
            for file in directory.iterdir():
                if file.is_dir():
                    _append_extensions_in_dir(file)
                elif (
                    file.suffix
                    and file.suffix not in exts
                    and file.suffix not in self.compilers.registered_compilers
                ):
                    exts.append(file.suffix)

        _append_extensions_in_dir(self.contracts_folder)
        if extensions:
            exts = [e for e in exts if e in extensions]

        return exts

    def lookup_path(self, key_contract_path: Path) -> Optional[Path]:
        """
        Figure out the full path of the contract from the given ``key_contract_path``.

        For example, give it ``HelloWorld`` and it returns
        ``<absolute-project-path>/contracts/HelloWorld.sol``.

        Another example is to give it ``contracts/HelloWorld.sol`` and it also
        returns ``<absolute-project-path>/contracts/HelloWorld.sol``.

        Args:
            key_contract_path (pathlib.Path): A sub-path to a contract.

        Returns:
            pathlib.Path: The path if it exists, else ``None``.
        """
        ext = key_contract_path.suffix or None

        def find_in_dir(dir_path: Path) -> Optional[Path]:
            for file_path in dir_path.iterdir():
                if file_path.is_dir():
                    return find_in_dir(file_path)

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
            Dict[str, :class:`~ape.types.contract.ContractType`]: A dictionary of contract names
            to their types for each compiled contract.
        """

        if isinstance(file_paths, Path):
            file_paths = [file_paths]

        # Load a cached or clean manifest (to use for caching)
        manifest = use_cache and self.cached_manifest or PackageManifest()
        cached_sources = manifest.sources or {}
        cached_contract_types = manifest.contractTypes or {}
        sources = {s for s in self.sources if s in file_paths} if file_paths else self.sources

        # If a file is deleted from ``sources`` but is in
        # ``cached_sources``, remove its corresponding ``contract_types`` by
        # using ``ContractType.sourceId`` and ``ContractType.sourcePath``
        deleted_sources = cached_sources.keys() - set(map(str, sources))

        # Filter out deleted sources
        contract_types = {
            n: ct for n, ct in cached_contract_types.items() if ct.sourceId not in deleted_sources
        }

        def file_needs_compiling(source: Path) -> bool:
            path = str(source)
            # New file added?
            if path not in cached_sources:
                return True

            # Recalculate checksum if it doesn't exist yet
            cached = cached_sources[path]
            cached.compute_checksum(algorithm="md5")

            assert cached.checksum  # to tell mypy this can't be None

            # File contents changed in source code folder?
            checksum = compute_checksum(
                source.read_bytes(),
                algorithm=cached.checksum.algorithm,
            )
            return checksum != cached.checksum.hash

        # NOTE: filter by checksum, etc., and compile what's needed
        #       to bring our cached manifest up-to-date
        needs_compiling = filter(file_needs_compiling, sources)
        contract_types.update(self.compilers.compile(list(needs_compiling)))

        # Update cached contract types & source code entries in cached manifest
        manifest.contractTypes = contract_types
        manifest.sources = _create_source_dict(sources)

        # NOTE: Cache the updated manifest to disk (so ``self.cached_manifest`` reads next time)
        self.manifest_cachefile.write_text(json.dumps(manifest.to_dict()))

        return contract_types

    @property
    def contracts(self) -> Dict[str, ContractType]:
        """
        A dictionary of contract names to their type.
        See :meth:`~ape.managers.project.ProjectManager.load_contracts` for more information.

        Returns:
            Dict[str, :class:`~ape.types.contract.ContractType`]
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
            raise AttributeError(f"{self.__class__.__name__} has no attribute '{attr_name}'.")

        return ContractContainer(  # type: ignore
            contract_type=contract_type,
            _provider=self.networks.active_provider,
            _converter=self.converter,
        )

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
            List[:class:`~ape.types.contract.Compiler`]
        """

        compilers = []

        for extension, compiler in self.compilers.registered_compilers.items():
            for version in compiler.get_versions(
                [p for p in self.sources if p.suffix == extension]
            ):
                compilers.append(Compiler(compiler.name, version))  # type: ignore

        return compilers

    # @property
    # def meta(self) -> PackageMeta:
    #     return PackageMeta(**self.config.get_config("ethpm").serialize())

    # def publish_manifest(self):
    #     manifest = self.manifest.to_dict()  # noqa: F841
    #     if not manifest["name"]:
    #         raise ProjectError("Need name to release manifest")
    #     if not manifest["version"]:
    #         raise ProjectError("Need version to release manifest")
    #     # TODO: Clean up manifest and minify it
    #     # TODO: Publish sources to IPFS and replace with CIDs
    #     # TODO: Publish to IPFS
