import json
from pathlib import Path
from typing import List, Optional, Set

from eth_utils import is_0x_prefixed
from ethpm_types import ContractType, HexBytes

from ape.api import CompilerAPI
from ape.exceptions import CompilerError, ContractLogicError
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
            source_path = (
                get_relative_path(path, base_path) if base_path and path.is_absolute() else path
            )
            source_id = str(source_path)
            code = path.read_text()
            if not code:
                continue

            try:
                # NOTE: Always set the source ID to the source of the JSON file
                #   to avoid manifest corruptions later on.
                contract_type = self.compile_code(
                    code,
                    base_path=base_path,
                    sourceId=source_id,
                )

                # NOTE: Try getting name/ ID from code-JSON first.
                #   That's why this is not part of `contract_type_overrides`.
                if not contract_type.name:
                    contract_type.name = path.stem

            except CompilerError:
                logger.warning(f"Unable to parse {ContractType.__name__} from '{source_id}'.")
                continue

            contract_types.append(contract_type)

        return contract_types

    def compile_code(
        self,
        code: str,
        base_path: Optional[Path] = None,
        **kwargs,
    ) -> ContractType:
        data = json.loads(code)
        if isinstance(data, list):
            # ABI JSON list
            contract_type_data = {"abi": data, **kwargs}

        elif isinstance(data, dict) and (
            "contractName" in data or "abi" in data or "sourceId" in data
        ):
            # Raw contract type JSON or raw compiler output.
            contract_type_data = {**data, **kwargs}

            if (
                "deploymentBytecode" not in contract_type_data
                or "runtimeBytecode" not in contract_type_data
            ):
                if "bin" in contract_type_data:
                    # Handle raw Solidity output.
                    deployment_bytecode = data["bin"]
                    runtime_bytecode = data["bin"]

                elif "bytecode" in contract_type_data or "bytecode_runtime" in contract_type_data:
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
            raise CompilerError(f"Unable to parse {ContractType.__name__}.")

        return ContractType(**contract_type_data)

    def enrich_error(self, err: ContractLogicError) -> ContractLogicError:
        if not (address := err.address) or not is_0x_prefixed(err.revert_message):
            return err

        # Check for ErrorABI.
        bytes_message = HexBytes(err.revert_message)
        selector = bytes_message[:4]
        input_data = bytes_message[4:]

        try:
            contract = self.chain_manager.contracts.instance_at(address)
        except Exception:
            return err

        if (
            not contract
            or not self.network_manager.active_provider
            or selector not in contract.contract_type.errors
        ):
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
            contract_address=address,
            source_traceback=err.source_traceback,
        )
