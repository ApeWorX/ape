import re
from typing import Optional, cast

from eth.exceptions import HeaderNotFound
from eth_tester.backends import PyEVMBackend  # type: ignore
from eth_tester.exceptions import TransactionFailed  # type: ignore
from eth_utils.exceptions import ValidationError
from web3 import EthereumTesterProvider, Web3
from web3.middleware import simple_cache_middleware
from web3.providers.eth_tester.defaults import API_ENDPOINTS
from web3.types import TxParams

from ape.api import ReceiptAPI, TestProviderAPI, TransactionAPI, Web3Provider
from ape.exceptions import (
    ContractLogicError,
    ProviderNotConnectedError,
    TransactionError,
    UnknownSnapshotError,
    VirtualMachineError,
)
from ape.types import SnapshotID
from ape.utils import gas_estimation_error_message

CHAIN_ID = API_ENDPOINTS["eth"]["chainId"]()


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
        self._web3.middleware_onion.add(simple_cache_middleware)

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
                raise TransactionError(message, base_err=ape_err, txn=txn) from ape_err

    @property
    def chain_id(self) -> int:
        if self.cached_chain_id is not None:
            return self.cached_chain_id
        elif hasattr(self.web3, "eth"):
            chain_id = self.web3.eth.chain_id
        else:
            chain_id = CHAIN_ID

        self.cached_chain_id = chain_id
        return chain_id

    @property
    def gas_price(self) -> int:
        return self.base_fee  # no miner tip

    @property
    def priority_fee(self) -> int:
        """Returns 0 because test chains do not care about priority fees."""
        return 0

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
            return self.web3.eth.call(tx_params, **call_kwargs)
        except ValidationError as err:
            raise VirtualMachineError(base_err=err) from err
        except TransactionFailed as err:
            raise self.get_virtual_machine_error(err, txn=txn) from err

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        try:
            txn_hash = self.web3.eth.send_raw_transaction(txn.serialize_transaction())
        except (ValidationError, TransactionFailed) as err:
            vm_err = self.get_virtual_machine_error(err, txn=txn)
            vm_err.txn = txn
            raise vm_err from err

        receipt = self.get_receipt(
            txn_hash.hex(), required_confirmations=txn.required_confirmations or 0
        )

        if receipt.failed:
            txn_dict = txn.dict()
            txn_dict["nonce"] += 1
            txn_params = cast(TxParams, txn_dict)

            # Replay txn to get revert reason
            try:
                self.web3.eth.call(txn_params)
            except (ValidationError, TransactionFailed) as err:
                vm_err = self.get_virtual_machine_error(err, txn=txn)
                vm_err.txn = txn
                raise vm_err from err

        self.chain_manager.history.append(receipt)
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
        self.evm_backend.time_travel(new_timestamp)

    def mine(self, num_blocks: int = 1):
        self.evm_backend.mine_blocks(num_blocks)

    def get_virtual_machine_error(self, exception: Exception, **kwargs) -> VirtualMachineError:
        txn = kwargs.get("txn")
        if isinstance(exception, ValidationError):
            match = self._CANNOT_AFFORD_GAS_PATTERN.match(str(exception))
            if match:
                txn_gas, bal = match.groups()
                sender = getattr(txn, "sender")
                new_message = (
                    f"Sender '{sender}' cannot afford txn gas {txn_gas} with account balance {bal}."
                )
                return VirtualMachineError(new_message, txn=txn)

            else:
                return VirtualMachineError(base_err=exception, txn=txn)

        elif isinstance(exception, TransactionFailed):
            err_message = str(exception).split("execution reverted: ")[-1] or None
            err_message = None if err_message == "b''" else err_message
            return ContractLogicError(revert_message=err_message, txn=txn)

        else:
            return VirtualMachineError(base_err=exception, txn=txn)
