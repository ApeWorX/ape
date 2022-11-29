import json
from pathlib import Path
from typing import List, Optional, Set

from ethpm_types import ContractType

from ape.api import CompilerAPI
from ape.logging import logger
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
        filepaths.sort()  # Sort to assist in reproducing consistent results.
        contract_types: List[ContractType] = []
        for path in filepaths:
            data = json.loads(path.read_text())
            source_path = (
                get_relative_path(path, base_path) if base_path and path.is_absolute() else path
            )
            source_id = str(source_path)
            if isinstance(data, list):
                # ABI JSON list
                contract_type_data = {"contractName": path.stem, "abi": data, "sourceId": source_id}

            elif isinstance(data, dict) and (
                "contractName" in data or "abi" in data or "sourceId" in data
            ):
                # Raw contract type JSON
                contract_type_data = data

            else:
                logger.warning(f"Unable to parse {ContractType.__name__} from '{source_id}'.")
                continue

            contract_type = ContractType(**contract_type_data)
            contract_types.append(contract_type)

        return contract_types
