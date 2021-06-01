import json
from pathlib import Path
from typing import Dict, List, Optional

import requests
from dataclassy import dataclass

from ape.types import Checksum, Compiler, ContractType, PackageManifest, Source  # PackageMeta
from ape.utils import compute_checksum

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
            raise Exception("Dependencies must have a name!")
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
                raise Exception("Corrupted Manifest")
            return PackageManifest.from_dict(manifest_json)

        else:
            return None

    # NOTE: Using these paths should handle the case when the folder doesn't exist
    @property
    def _contracts_folder(self) -> Path:
        return self.path / "contracts"

    @property
    def sources(self) -> List[Path]:
        files: List[Path] = []
        for extension in self.compilers.registered_compilers:
            files.extend(self._contracts_folder.rglob("*" + extension))

        return files

    def load_contracts(self, use_cache: bool = True) -> Dict[str, ContractType]:
        # Load a cached or clean manifest (to use for caching)
        manifest = use_cache and self.cached_manifest or PackageManifest()
        cached_sources = manifest.sources or {}
        cached_contract_types = manifest.contractTypes or {}

        # If a file is deleted from `self.sources` but is in `cached_sources`,
        # remove its corresponding `contract_types` by using
        # `ContractType.sourceId` and `ContractType.sourcePath`
        deleted_sources = cached_sources.keys() - set(map(str, self.sources))
        contract_types = {}
        for name, ct in cached_contract_types.items():
            if ct.sourceId in deleted_sources:
                pass  # this contract's source code file was deleted
            else:
                contract_types[name] = ct

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
        needs_compiling = filter(file_needs_compiling, self.sources)
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
            for source in self.sources
        }
        manifest.sources = cached_sources

        # NOTE: Cache the updated manifest to disk (so `self.cached_manifest` reads next time)
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
            raise AttributeError(f"{self.__class__.__name__} has no attribute '{attr_name}'")

    @property
    def _interfaces_folder(self) -> Path:
        return self.path / "interfaces"

    @property
    def _scripts_folder(self) -> Path:
        return self.path / "scripts"

    @property
    def _tests_folder(self) -> Path:
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
    #         raise Exception("Need name to release manifest")
    #     if not manifest["version"]:
    #         raise Exception("Need version to release manifest")
    #     # TODO: Clean up manifest and minify it
    #     # TODO: Publish sources to IPFS and replace with CIDs
    #     # TODO: Publish to IPFS
