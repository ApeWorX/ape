from typing import Any, Iterator

from eth_tester.backends import PyEVMBackend
from eth_tester.exceptions import TransactionFailed
from hexbytes import HexBytes
from web3 import EthereumTesterProvider, Web3

from ape.api import ProviderAPI, ReceiptAPI, TransactionAPI
from ape.exceptions import ContractLogicError
from ape.utils import DEVELOPMENT_MNEMONIC, generate_dev_accounts


class TestEVMBackend(PyEVMBackend):
    """
    An EVM backend populated with accounts using the test mnemonic.
    """

    def __init__(self, initial_balance: int = 10000000000000000000000):
        dev_accounts = generate_dev_accounts()
        account_data = {
            HexBytes(a["address"]): {
                "balance": initial_balance,
                "nonce": 0,
                "code": b"",
                "storage": {},
            }
            for a in dev_accounts
        }
        super().__init__(genesis_state=account_data, mnemonic=DEVELOPMENT_MNEMONIC)


class LocalNetwork(ProviderAPI):
    _web3: Web3 = None  # type: ignore

    def connect(self):
        pass

    def disconnect(self):
        pass

    def update_settings(self, new_settings: dict):
        pass

    def __post_init__(self):
        self._backend = TestEVMBackend()
        self._web3 = Web3(EthereumTesterProvider(ethereum_tester=self._backend))

    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        try:
            return self._web3.eth.estimate_gas(txn.as_dict())  # type: ignore
        except TransactionFailed as err:
            err_message = str(err).split("execution reverted: ")[-1]
            raise ContractLogicError(err_message) from err

    @property
    def chain_id(self) -> int:
        return self._web3.eth.chain_id

    @property
    def gas_price(self):
        # NOTE: Test chain doesn't care about gas prices
        return 0

    def get_nonce(self, address: str) -> int:
        return self._web3.eth.get_transaction_count(address)  # type: ignore

    def get_balance(self, address: str) -> int:
        return self._web3.eth.get_balance(address)  # type: ignore

    def get_code(self, address: str) -> bytes:
        return self._web3.eth.get_code(address)  # type: ignore

    def send_call(self, txn: TransactionAPI) -> bytes:
        data = txn.as_dict()
        if "gas" not in data or data["gas"] == 0:
            data["gas"] = int(1e12)
        return self._web3.eth.call(data)

    def get_transaction(self, txn_hash: str) -> ReceiptAPI:
        # TODO: Work on API that let's you work with ReceiptAPI and re-send transactions
        receipt = self._web3.eth.wait_for_transaction_receipt(txn_hash)  # type: ignore
        txn = self._web3.eth.get_transaction(txn_hash)  # type: ignore
        return self.network.ecosystem.receipt_class.decode({**txn, **receipt})

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        try:
            txn_hash = self._web3.eth.send_raw_transaction(txn.encode())
        except TransactionFailed as err:
            err_message = str(err).split("execution reverted: ")[-1]
            raise ContractLogicError(err_message) from err

        return self.get_transaction(txn_hash.hex())

    def get_events(self, **filter_params) -> Iterator[dict]:
        return iter(self._web3.eth.get_logs(filter_params))  # type: ignore

    def snapshot(self) -> Any:
        return self._backend.take_snapshot()

    def revert(self, snapshot_id: Any):
        return self._backend.revert_to_snapshot(snapshot_id)
