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
        contract_types: List[ContractType] = []
        for path in filepaths:
            abi = json.loads(path.read_text())

            if base_path:
                source_id = str(get_relative_path(path.absolute(), base_path))
                contract_name = source_id.replace(".json", "").replace("/", ".")
            else:
                source_id = str(path)
                contract_name = path.stem

            if not isinstance(abi, list):
                logger.warning(f"Not a valid ABI interface JSON file (sourceID={source_id}).")

            else:
                contract = ContractType.parse_obj(
                    {
                        "contractName": contract_name,
                        "abi": abi,
                        "sourceId": source_id,
                    }
                )

                contract_types.append(contract)

        return contract_types
