import json
from pathlib import Path
from typing import List

from ape.api.compiler import CompilerAPI
from ape.types import ContractType, PackageManifest


class PackageCompiler(CompilerAPI):
    @property
    def name(self) -> str:
        return "ethpm"

    @property
    def versions(self) -> List[str]:
        # NOTE: This bypasses the serialization of this compiler into the package manifest's
        #       `compilers` field. You should not do this with a real compiler plugin.
        return []

    def compile(self, filepaths: List[Path]) -> List[ContractType]:
        contract_types: List[ContractType] = []
        for path in filepaths:
            data = json.load(path.open())
            if "manifest" in data:
                manifest = PackageManifest.from_dict(data)

                if manifest.contractTypes:  # type: ignore
                    contract_types.extend(manifest.contractTypes.values())  # type: ignore

            else:
                contract_types.append(
                    ContractType(  # type: ignore
                        contractName=path.stem,
                        abi=json.load(path.open()),
                    )
                )

        return contract_types
