import json
from pathlib import Path
from typing import List, Set

from ethpm_types.contract_type import ContractType

from ape.api import CompilerAPI
from ape.exceptions import CompilerError


class InterfaceCompiler(CompilerAPI):
    @property
    def name(self) -> str:
        return "ethpm"

    def get_versions(self, all_paths: List[Path]) -> Set[str]:
        # NOTE: This bypasses the serialization of this compiler into the package manifest's
        #       ``compilers`` field. You should not do this with a real compiler plugin.
        return set()

    def compile(self, filepaths: List[Path]) -> List[ContractType]:
        contract_types: List[ContractType] = []
        for path in filepaths:
            with path.open() as f:
                data = json.load(f)

            if not isinstance(data, list):
                raise CompilerError("Not a valid ABI interface JSON file.")

            else:
                contract_types.append(
                    ContractType(  # type: ignore
                        name=path.stem,
                        abi=data,
                        source_id=str(path),
                    )
                )

        return contract_types
