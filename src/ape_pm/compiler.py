import json
from pathlib import Path
from typing import List

from ape.api.compiler import CompilerAPI
from ape.types import ContractType, PackageManifest


class PackageCompiler(CompilerAPI):
    @property
    def name(self) -> str:
        return "ethpm"

    def compile(self, filepaths: List[Path]) -> List[ContractType]:
        contract_types: List[ContractType] = []
        for path in filepaths:
            manifest = PackageManifest.from_dict(json.loads(path.read_text()))

            if manifest.contractTypes:
                contract_types.extend(manifest.contractTypes.values())

        return contract_types
