import json
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dataclassy import dataclass

from ape.types import Checksum, Compiler, ContractType, PackageManifest, Source
from ape.utils import compute_checksum

from ..exceptions import ProjectError
from .compilers import CompilerManager
from .config import ConfigManager


@dataclass
class ProjectManager:
    path: Path
    config: ConfigManager
    compilers: CompilerManager

    dependencies: Dict[str, PackageManifest] = dict()

    def __post_init__(self):
        if isinstance(self.path, str):
            self.path = Path(self.path)

        self.dependencies = {
            manifest.name: manifest
            for manifest in map(self._extract_manifest, self.config.dependencies)
        }

    def _extract_manifest(self, manifest_uri: str) -> PackageManifest:
        manifest_dict = requests.get(manifest_uri).json()
        # TODO: Handle non-manifest URLs e.g. Ape/Brownie projects, Hardhat/Truffle projects, etc.
        if "name" not in manifest_dict:
            raise ProjectError("Dependencies must have a name.")

        return PackageManifest.from_dict(manifest_dict)

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
        file_name = self.config.name or "__local__"
        return self._cache_folder / (file_name + ".json")

    @property
    def cached_manifest(self) -> Optional[PackageManifest]:
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
        return self.path / "contracts"

    @property
    def sources(self) -> List[Path]:
        """All the source files in the project.
        Excludes files with extensions that don't have a registered compiler.
        """
        files: List[Path] = []
        for extension in self.compilers.registered_compilers:
            files.extend(self.contracts_folder.rglob("*" + extension))

        return files

    @property
    def sources_missing(self) -> bool:
        return not self.contracts_folder.exists() or not self.contracts_folder.iterdir()

    @property
    def extensions_with_missing_compilers(self) -> List[str]:
        """All file extensions in the `contracts/` directory (recursively)
        that do not correspond to a registered compiler."""
        extensions = []

        def _append_extensions_in_dir(directory: Path):
            for file in directory.iterdir():
                if file.is_dir():
                    _append_extensions_in_dir(file)
                elif (
                    file.suffix
                    and file.suffix not in extensions
                    and file.suffix not in self.compilers.registered_compilers
                ):
                    extensions.append(file.suffix)

        _append_extensions_in_dir(self.contracts_folder)
        return extensions

    def lookup_path(self, key_contract_path: Path) -> Optional[Path]:
        """
        Figures out the full path of the contract from the given ``key_contract_path``.

        For example, give it ``HelloWorld``, it returns
        ``<absolute-project-path>/contracts/HelloWorld.sol``.

        Another example is to give it ``contracts/HelloWorld.sol`` and it also
        returns ``<absolute-project-path>/contracts/HelloWorld.sol``.
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
        self, file_paths: Optional[List[Path]] = None, use_cache: bool = True
    ) -> Dict[str, ContractType]:
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
        cached_sources = {
            str(source): Source(  # type: ignore
                checksum=Checksum(  # type: ignore
                    algorithm="md5", hash=compute_checksum(source.read_bytes())
                ),
                urls=[],
            )
            for source in sources
        }
        manifest.sources = cached_sources

        # NOTE: Cache the updated manifest to disk (so ``self.cached_manifest`` reads next time)
        self.manifest_cachefile.write_text(json.dumps(manifest.to_dict()))

        return contract_types

    @property
    def contracts(self) -> Dict[str, ContractType]:
        return self.load_contracts()

    def __getattr__(self, attr_name: str):
        contracts = self.load_contracts()
        if attr_name in contracts:
            return contracts[attr_name]
        elif attr_name in self.dependencies:
            return self.dependencies[attr_name]
        else:
            raise AttributeError(f"{self.__class__.__name__} has no attribute '{attr_name}'.")

    @property
    def interfaces_folder(self) -> Path:
        return self.path / "interfaces"

    @property
    def scripts_folder(self) -> Path:
        return self.path / "scripts"

    @property
    def tests_folder(self) -> Path:
        return self.path / "tests"

    # TODO: Make this work for generating and caching the manifest file
    @property
    def compiler_data(self) -> List[Compiler]:
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
