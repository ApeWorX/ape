import json
from pathlib import Path
from typing import List, Set

from ape.api.compiler import CompilerAPI
from ape.types import ContractType


class InterfaceCompiler(CompilerAPI):
    @property
    def name(self) -> str:
        return "ethpm"

    def get_versions(self, all_paths: List[Path]) -> Set[str]:
        # NOTE: This bypasses the serialization of this compiler into the package manifest's
        #       `compilers` field. You should not do this with a real compiler plugin.
        return set()

    def compile(self, filepaths: List[Path]) -> List[ContractType]:
        contract_types: List[ContractType] = []
        for path in filepaths:
            with path.open() as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise Exception("Not a valid ABI interface JSON file")

            else:
                contract_types.append(
                    ContractType(  # type: ignore
                        contractName=path.stem,
                        abi=data,
                        sourceId=str(path),
                    )
                )

        return contract_types
