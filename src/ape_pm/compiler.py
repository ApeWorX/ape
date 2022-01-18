import json
from pathlib import Path
from typing import List, Optional, Set

from ethpm_types import ABI, ContractType
from pydantic import parse_obj_as

from ape.api import CompilerAPI
from ape.exceptions import CompilerError
from ape.utils import get_relative_path


class InterfaceCompiler(CompilerAPI):
    @property
    def name(self) -> str:
        return "ethpm"

    def get_versions(self, all_paths: List[Path]) -> Set[str]:
        # NOTE: This bypasses the serialization of this compiler into the package manifest's
        #       ``compilers`` field. You should not do this with a real compiler plugin.
        return set()

    def compile(
        self, filepaths: List[Path], base_path: Optional[Path] = None
    ) -> List[ContractType]:
        contract_types: List[ContractType] = []
        for path in filepaths:
            with path.open() as f:
                data = json.load(f)

            source_id = (
                str(get_relative_path(path, base_path))
                if base_path and path.is_absolute()
                else str(path)
            )
            if not isinstance(data, list):
                raise CompilerError("Not a valid ABI interface JSON file.")

            else:
                contract = ContractType(  # type: ignore
                    contractName=path.stem,
                    abi=parse_obj_as(List[ABI], data),
                    sourceId=source_id,
                )

                contract_types.append(contract)

        return contract_types
