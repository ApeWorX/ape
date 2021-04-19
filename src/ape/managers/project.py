from pathlib import Path
from typing import Dict, List

from dataclassy import dataclass

from ape.types import ContractType  # Compiler, PackageManifest, PackageMeta

from .compilers import CompilerManager
from .config import ConfigManager


@dataclass
class ProjectManager:
    path: Path
    config: ConfigManager
    compilers: CompilerManager

    depedendencies: Dict[str, "ProjectManager"] = dict()

    def __init__(self):
        pass  # Look for depedencies from config

    def __str__(self) -> str:
        return f'Project("{self.path}")'

    def _cache_folder(self) -> Path:
        folder = self.path / ".build"
        # NOTE: If we use the cache folder, we expect it to exist
        folder.mkdir(exist_ok=True)
        return folder

    # NOTE: Using these paths should handle the case when the folder doesn't exist
    @property
    def _contracts_folder(self) -> Path:
        return self.path / "contracts"

    @property
    def sources(self) -> List[Path]:
        files = []
        for extension in self.compilers.registered_compilers:
            for f in self._contracts_folder.rglob("*" + extension):
                files.append(f.relative_to(self.path))

        return files

    @property
    def contracts(self) -> Dict[str, ContractType]:
        contract_types = {}
        for filepath in self.sources:
            contract_type = self.compilers.compile(filepath)

            if contract_type.contractName in contract_types:
                raise  # ContractType collision across compiler plugins

            contract_types[contract_type.contractName] = contract_type

        return contract_types

    def _interfaces_folder(self) -> Path:
        return self.path / "interfaces"

    def _scripts_folder(self) -> Path:
        return self.path / "scripts"

    def _tests_folder(self) -> Path:
        return self.path / "tests"

    # TODO: Make this work for generating and caching the manifest file

    # @property
    # def meta(self) -> PackageMeta:
    #     return PackageMeta(**self.config.get_config("ethpm").serialize())

    # @property
    # def manifest(self) -> PackageManifest:
    #     return PackageManifest(
    #         name=self.config.name,
    #         version=self.config.version,
    #         meta=self.meta,
    #         sources=self.sources,
    #         contractTypes=list(self.contracts.values()),
    #         compilers=list(
    #             Compiler(c.name, c.version)  # type: ignore
    #             for c in self.compilers.registered_compilers.values()
    #         ),
    #     )

    # def publish_manifest(self):
    #     manifest = self.manifest.to_dict()  # noqa: F841
    #     # TODO: Clean up manifest
    #     # TODO: Publish sources to IPFS and replace with CIDs
    #     # TODO: Publish to IPFS
