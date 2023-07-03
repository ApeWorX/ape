import re
from ast import literal_eval
from typing import Optional, cast

from eth.exceptions import HeaderNotFound
from eth_tester.backends import PyEVMBackend  # type: ignore
from eth_tester.exceptions import TransactionFailed  # type: ignore
from eth_utils import is_0x_prefixed
from eth_utils.exceptions import ValidationError
from ethpm_types import HexBytes
from lazyasd import LazyObject  # type: ignore
from web3 import EthereumTesterProvider, Web3
from web3.exceptions import ContractPanicError
from web3.providers.eth_tester.defaults import API_ENDPOINTS
from web3.types import TxParams

from ape.api import ReceiptAPI, TestProviderAPI, TransactionAPI, Web3Provider
from ape.exceptions import (
    ContractLogicError,
    ProviderError,
    ProviderNotConnectedError,
    TransactionError,
    UnknownSnapshotError,
    VirtualMachineError,
)
from ape.types import SnapshotID
from ape.utils import gas_estimation_error_message

CHAIN_ID = LazyObject(lambda: API_ENDPOINTS["eth"]["chainId"](), globals(), "CHAIN_ID")


class LocalProvider(TestProviderAPI, Web3Provider):
    _evm_backend: Optional[PyEVMBackend] = None
    _CANNOT_AFFORD_GAS_PATTERN = re.compile(
        r"Sender b'[\\*|\w]*' cannot afford txn gas (\d+) with account balance (\d+)"
    )
    _INVALID_NONCE_PATTERN = re.compile(r"Invalid transaction nonce: Expected (\d+), but got (\d+)")

    @property
    def evm_backend(self) -> PyEVMBackend:
        if self._evm_backend is None:
            raise ProviderNotConnectedError()

        return self._evm_backend

    def connect(self):
        if self._web3 is not None:
            return

        self._evm_backend = PyEVMBackend.from_mnemonic(
            mnemonic=self.config["mnemonic"],
            num_accounts=self.config["number_of_accounts"],
        )
        self._web3 = Web3(EthereumTesterProvider(ethereum_tester=self._evm_backend))

    def disconnect(self):
        self.cached_chain_id = None
        self._web3 = None
        self._evm_backend = None

    def update_settings(self, new_settings: dict):
        pass

    def estimate_gas_cost(self, txn: TransactionAPI, **kwargs) -> int:
        if isinstance(self.network.gas_limit, int):
            return self.network.gas_limit

        elif self.network.gas_limit == "max":
            block = self.web3.eth.get_block("latest")
            return block["gasLimit"]

        block_id = kwargs.pop("block_identifier", None)
        estimate_gas = self.web3.eth.estimate_gas
        txn_dict = txn.dict()
        if txn_dict.get("gas") == "auto":
            # Remove from dict before estimating
            txn_dict.pop("gas")

        try:
            return estimate_gas(txn_dict, block_identifier=block_id)  # type: ignore
        except (ValidationError, TransactionFailed) as err:
            ape_err = self.get_virtual_machine_error(err, txn=txn)
            gas_match = self._INVALID_NONCE_PATTERN.match(str(ape_err))
            if gas_match:
                # Sometimes, EthTester is confused about the sender nonce
                # during gas estimation. Retry using the "expected" gas
                # and then set it back.
                expected_nonce, actual_nonce = gas_match.groups()
                txn.nonce = int(expected_nonce)
                value = estimate_gas(txn.dict(), block_identifier=block_id)  # type: ignore
                txn.nonce = int(actual_nonce)
                return value

            elif isinstance(ape_err, ContractLogicError):
                raise ape_err from err
            else:
                message = gas_estimation_error_message(ape_err)
                raise TransactionError(
                    message, base_err=ape_err, txn=txn, source_traceback=ape_err.source_traceback
                ) from ape_err

    @property
    def chain_id(self) -> int:
        if self.cached_chain_id is not None:
            return self.cached_chain_id
        elif hasattr(self.web3, "eth"):
            chain_id = self.web3.eth.chain_id
        else:
            chain_id = CHAIN_ID  # type: ignore

        self.cached_chain_id = chain_id
        return chain_id

    @property
    def gas_price(self) -> int:
        return self.base_fee  # no miner tip

    @property
    def priority_fee(self) -> int:
        """Returns 0 because test chains do not care about priority fees."""
        return 0

    @property
    def base_fee(self) -> int:
        """
        EthTester does not implement RPC `eth_feeHistory`.
        Returns the last base fee on chain.
        """
        return self._get_last_base_fee()

    def send_call(self, txn: TransactionAPI, **kwargs) -> bytes:
        data = txn.dict(exclude_none=True)
        block_id = kwargs.pop("block_identifier", None)
        state = kwargs.pop("state_override", None)
        call_kwargs = {"block_identifier": block_id, "state_override": state}

        # Remove unneeded properties
        data.pop("gas", None)
        data.pop("gasLimit", None)
        data.pop("maxFeePerGas", None)
        data.pop("maxPriorityFeePerGas", None)

        tx_params = cast(TxParams, data)

        try:
            result = self.web3.eth.call(tx_params, **call_kwargs)
        except ValidationError as err:
            raise VirtualMachineError(base_err=err) from err
        except (TransactionFailed, ContractPanicError) as err:
            raise self.get_virtual_machine_error(err, txn=txn) from err

        self._increment_call_func_coverage_hit_count(txn)
        return result

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        try:
            txn_hash = self.web3.eth.send_raw_transaction(txn.serialize_transaction())
        except (ValidationError, TransactionFailed) as err:
            vm_err = self.get_virtual_machine_error(err, txn=txn)
            raise vm_err from err

        receipt = self.get_receipt(
            txn_hash.hex(), required_confirmations=txn.required_confirmations or 0
        )

        # NOTE: Caching must happen before error enrichment.
        self.chain_manager.history.append(receipt)

        if receipt.failed:
            txn_dict = txn.dict()
            txn_dict["nonce"] += 1
            txn_params = cast(TxParams, txn_dict)

            # Replay txn to get revert reason
            try:
                self.web3.eth.call(txn_params)
            except (ValidationError, TransactionFailed) as err:
                vm_err = self.get_virtual_machine_error(err, txn=receipt)
                raise vm_err from err

        return receipt

    def snapshot(self) -> SnapshotID:
        return self.evm_backend.take_snapshot()

    def revert(self, snapshot_id: SnapshotID):
        if snapshot_id:
            current_hash = self.get_block("latest").hash
            if current_hash != snapshot_id:
                try:
                    return self.evm_backend.revert_to_snapshot(snapshot_id)
                except HeaderNotFound:
                    raise UnknownSnapshotError(snapshot_id)

    def set_timestamp(self, new_timestamp: int):
        current = self.get_block("pending").timestamp
        if new_timestamp == current:
            # Is the same, treat as a noop.
            return

        try:
            self.evm_backend.time_travel(new_timestamp)
        except ValidationError as err:
            pattern = re.compile(
                r"timestamp must be strictly later than parent, "
                r"but is 0 seconds before\.\n- child\s{2}: (\d*)\n- parent : (\d*)\.\s*"
            )
            if match := re.match(pattern, str(err)):
                if groups := match.groups():
                    if groups[0].strip() == groups[1].strip():
                        # Handle race condition when block headers are the same.
                        # Treat as noop, same as pre-check.
                        return

            raise ProviderError(f"Failed to time travel: {err}") from err

    def mine(self, num_blocks: int = 1):
        self.evm_backend.mine_blocks(num_blocks)

    def get_virtual_machine_error(self, exception: Exception, **kwargs) -> VirtualMachineError:
        if isinstance(exception, ValidationError):
            match = self._CANNOT_AFFORD_GAS_PATTERN.match(str(exception))
            if match:
                txn_gas, bal = match.groups()
                sender = getattr(kwargs["txn"], "sender")
                new_message = (
                    f"Sender '{sender}' cannot afford txn gas {txn_gas} with account balance {bal}."
                )
                return VirtualMachineError(new_message, base_err=exception, **kwargs)

            else:
                return VirtualMachineError(base_err=exception, **kwargs)

        elif isinstance(exception, ContractPanicError):
            # If the ape-solidity plugin is installed, we are able to enrich the data.
            message = exception.message
            raw_data = exception.data if isinstance(exception.data, str) else "0x"
            error = ContractLogicError(base_err=exception, revert_message=raw_data, **kwargs)
            enriched_error = self.compiler_manager.enrich_error(error)
            if is_0x_prefixed(enriched_error.message):
                # Failed to enrich. Use nicer message from web3.py.
                enriched_error.message = message or enriched_error.message

            return enriched_error

        elif isinstance(exception, TransactionFailed):
            err_message = str(exception).split("execution reverted: ")[-1] or None

            if err_message and err_message.startswith("b'") and err_message.endswith("'"):
                # Convert stringified bytes str like `"b'\\x82\\xb4)\\x00'"` to `"0x82b42900"`.
                # (Notice the `b'` is within the `"` on the first str).
                err_message = HexBytes(literal_eval(err_message)).hex()

            err_message = TransactionError.DEFAULT_MESSAGE if err_message == "0x" else err_message
            contract_err = ContractLogicError(
                base_err=exception, revert_message=err_message, **kwargs
            )
            return self.compiler_manager.enrich_error(contract_err)

        else:
            return VirtualMachineError(base_err=exception, **kwargs)
