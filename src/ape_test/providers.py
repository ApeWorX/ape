from eth_tester.backends import PyEVMBackend  # type: ignore
from eth_tester.exceptions import TransactionFailed  # type: ignore
from eth_utils.exceptions import ValidationError
from web3 import EthereumTesterProvider, Web3
from web3.middleware import simple_cache_middleware
from web3.providers.eth_tester.defaults import API_ENDPOINTS

from ape.api import ReceiptAPI, TestProviderAPI, TransactionAPI, Web3Provider
from ape.exceptions import ContractLogicError, OutOfGasError, TransactionError, VirtualMachineError
from ape.types import SnapshotID
from ape.utils import gas_estimation_error_message


class LocalProvider(TestProviderAPI, Web3Provider):

    _tester: PyEVMBackend

    def __init__(self, **data) -> None:
        super().__init__(**data)
        self._tester = PyEVMBackend.from_mnemonic(
            mnemonic=self.config["mnemonic"],
            num_accounts=self.config["number_of_accounts"],
        )

    def connect(self):
        self._web3 = Web3(EthereumTesterProvider(ethereum_tester=self._tester))
        self._web3.middleware_onion.add(simple_cache_middleware)

    def disconnect(self):
        self.cached_chain_id = None
        self._web3 = None

    def update_settings(self, new_settings: dict):
        pass

    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        try:
            result = self.web3.eth.estimate_gas(txn.dict())  # type: ignore
            return result
        except ValidationError as err:
            message = gas_estimation_error_message(err)
            raise TransactionError(base_err=err, message=message) from err
        except TransactionFailed as err:
            raise self.get_virtual_machine_error(err) from err

    @property
    def chain_id(self) -> int:
        if self.cached_chain_id is not None:
            return self.cached_chain_id
        elif hasattr(self.web3, "eth"):
            chain_id = self.web3.eth.chain_id
        else:
            default_value = API_ENDPOINTS["eth"]["chainId"]()
            chain_id = int(default_value, 16)

        self.cached_chain_id = chain_id
        return chain_id

    @property
    def gas_price(self) -> int:
        return self.base_fee  # no miner tip

    @property
    def priority_fee(self) -> int:
        """Returns 0 because test chains do not care about priority fees."""
        return 0

    def send_call(self, txn: TransactionAPI) -> bytes:
        data = txn.dict(exclude_none=True)
        if "gas" not in data or data["gas"] == 0:
            data["gas"] = int(1e12)

        try:
            return self.web3.eth.call(data)
        except ValidationError as err:
            raise VirtualMachineError(base_err=err) from err
        except TransactionFailed as err:
            raise self.get_virtual_machine_error(err) from err

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        try:
            txn_hash = self.web3.eth.send_raw_transaction(txn.serialize_transaction())
        except ValidationError as err:
            raise VirtualMachineError(base_err=err) from err
        except TransactionFailed as err:
            raise self.get_virtual_machine_error(err) from err

        receipt = self.get_transaction(
            txn_hash.hex(), required_confirmations=txn.required_confirmations or 0
        )
        if txn.gas_limit is not None and receipt.ran_out_of_gas:
            raise OutOfGasError()

        self._try_track_receipt(receipt)
        return receipt

    def snapshot(self) -> SnapshotID:
        return self._tester.take_snapshot()

    def revert(self, snapshot_id: SnapshotID):
        if snapshot_id:
            current_hash = self.get_block("latest").hash
            if current_hash != snapshot_id:
                return self._tester.revert_to_snapshot(snapshot_id)

    def set_timestamp(self, new_timestamp: int):
        self._tester.time_travel(new_timestamp)

    def mine(self, num_blocks: int = 1):
        self._tester.mine_blocks(num_blocks)

    def get_virtual_machine_error(self, web3_err: TransactionFailed) -> VirtualMachineError:
        err_message = str(web3_err).split("execution reverted: ")[-1] or None
        err_message = None if err_message == "b''" else err_message
        return ContractLogicError(revert_message=err_message)
