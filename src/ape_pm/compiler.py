import json
from pathlib import Path
from typing import Dict, List, Optional, Set

from eth_utils import is_0x_prefixed
from ethpm_types import ContractType, HexBytes

from ape.api import CompilerAPI
from ape.exceptions import ContractLogicError
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
        contract_type_data: Dict
        for path in filepaths:
            data = json.loads(path.read_text())
            source_path = (
                get_relative_path(path, base_path) if base_path and path.is_absolute() else path
            )
            source_id = str(source_path)
            if isinstance(data, list):
                # ABI JSON list
                contract_type_data = {"abi": data, "contractName": path.stem, "sourceId": source_id}

            elif isinstance(data, dict) and (
                "contractName" in data or "abi" in data or "sourceId" in data
            ):
                # Raw contract type JSON or raw compiler output.
                contract_type_data = data
                if "contractName" not in contract_type_data:
                    contract_type_data["contractName"] = path.stem
                if "sourceId" not in contract_type_data:
                    contract_type_data["sourceId"] = source_id

                if (
                    "deploymentBytecode" not in contract_type_data
                    or "runtimeBytecode" not in contract_type_data
                ):
                    if "bin" in contract_type_data:
                        # Handle raw Solidity output.
                        deployment_bytecode = data["bin"]
                        runtime_bytecode = data["bin"]

                    elif (
                        "bytecode" in contract_type_data or "bytecode_runtime" in contract_type_data
                    ):
                        # Handle raw Vyper output.
                        deployment_bytecode = contract_type_data.pop("bytecode", None)
                        runtime_bytecode = contract_type_data.pop("bytecode_runtime", None)

                    else:
                        deployment_bytecode = None
                        runtime_bytecode = None

                    if deployment_bytecode:
                        contract_type_data["deploymentBytecode"] = {"bytecode": deployment_bytecode}
                    if runtime_bytecode:
                        contract_type_data["runtimeBytecode"] = {"bytecode": runtime_bytecode}

            else:
                logger.warning(f"Unable to parse {ContractType.__name__} from '{source_id}'.")
                continue

            contract_type = ContractType(**contract_type_data)
            contract_types.append(contract_type)

        return contract_types

    def enrich_error(self, err: ContractLogicError) -> ContractLogicError:
        if not is_0x_prefixed(err.revert_message):
            return err

        # Check for ErrorABI.
        bytes_message = HexBytes(err.revert_message)
        selector = bytes_message[:4]
        input_data = bytes_message[4:]
        address = err.contract_address or getattr(err.txn, "receiver", None)
        if not address:
            return err

        if not self.network_manager.active_provider:
            # Connection required.
            return err

        contract = self.chain_manager.contracts.instance_at(address)
        if not contract:
            return err

        if selector not in contract.contract_type.errors:
            # Not an ErrorABI selector.
            return err

        ecosystem = self.provider.network.ecosystem
        abi = contract.contract_type.errors[selector]
        inputs = ecosystem.decode_calldata(abi, input_data)
        error_class = contract.get_error_by_signature(abi.signature)
        return error_class(
            abi,
            inputs,
            txn=err.txn,
            trace=err.trace,
            contract_address=err.contract_address,
            source_traceback=err.source_traceback,
        )
