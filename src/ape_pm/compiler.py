import json
from collections.abc import Iterable, Iterator
from json import JSONDecodeError
from pathlib import Path
from typing import Optional

from eth_pydantic_types import HexBytes
from eth_utils import is_0x_prefixed
from ethpm_types import ContractType

from ape.api.compiler import CompilerAPI
from ape.exceptions import CompilerError, ContractLogicError
from ape.logging import logger
from ape.managers.project import ProjectManager
from ape.utils.os import get_relative_path


class InterfaceCompiler(CompilerAPI):
    """
    A compiler plugin for interface JSONs (ABIs). Also, this
    compiler can "compile" already-compiled ``ContractType``
    JSON files.
    """

    @property
    def name(self) -> str:
        return "ethpm"

    def get_versions(self, all_paths: Iterable[Path]) -> set[str]:
        # NOTE: This bypasses the serialization of this compiler into the package manifest's
        #       ``compilers`` field. You should not do this with a real compiler plugin.
        return set()

    def compile(
        self,
        contract_filepaths: Iterable[Path],
        project: Optional["ProjectManager"],
        settings: Optional[dict] = None,
    ) -> Iterator[ContractType]:
        project = project or self.local_project
        source_ids = {
            p: f"{get_relative_path(p, project.path.absolute())}" if p.is_absolute() else str(p)
            for p in contract_filepaths
        }
        logger.info(f"Compiling {', '.join(source_ids.values())}.")
        for path in contract_filepaths:
            if not path.is_file() and (project.path / path).is_file():
                # Was given a relative path.
                src_path = project.path / path
            elif not path.is_file():
                raise CompilerError(f"'{path}' is not a file.")
            else:
                src_path = path

            code = src_path.read_text()
            source_id = source_ids[path]
            contract_type = self.compile_code(code, project=project, sourceId=source_id)

            # NOTE: Try getting name/ ID from code-JSON first.
            #   That's why this is not part of `**kwargs` in `compile_code()`.
            contract_type.name = contract_type.name or src_path.stem
            yield contract_type

    def compile_code(
        self,
        code: str,
        project: Optional[ProjectManager] = None,
        **kwargs,
    ) -> ContractType:
        code = code or "[]"
        try:
            data = json.loads(code)
        except JSONDecodeError as err:
            raise CompilerError(str(err)) from err

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
            trace=lambda: err.trace,
            contract_address=address,
            source_traceback=lambda: err.source_traceback,
        )
