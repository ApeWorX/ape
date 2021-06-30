from typing import Iterator

from web3 import EthereumTesterProvider, Web3  # type: ignore

from ape.api import ProviderAPI, ReceiptAPI, TransactionAPI


class LocalNetwork(ProviderAPI):
    _web3: Web3 = None  # type: ignore

    def connect(self):
        pass

    def disconnect(self):
        pass

    def update_settings(self, new_settings: dict):
        pass

    def __post_init__(self):
        self._web3 = Web3(EthereumTesterProvider())

    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        return self._web3.eth.estimate_gas(txn.as_dict())  # type: ignore

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
        if data["gas"] == 0:
            data["gas"] = int(1e12)
        return self._web3.eth.call(data)

    def get_transaction(self, txn_hash: str) -> ReceiptAPI:
        # TODO: Work on API that let's you work with ReceiptAPI and re-send transactions
        receipt = self._web3.eth.wait_for_transaction_receipt(txn_hash)  # type: ignore
        txn = self._web3.eth.get_transaction(txn_hash)  # type: ignore
        return self.network.ecosystem.receipt_class.decode({**txn, **receipt})

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        txn_hash = self._web3.eth.send_raw_transaction(txn.encode())
        return self.get_transaction(txn_hash.hex())

    def get_events(self, **filter_params) -> Iterator[dict]:
        return iter(self._web3.eth.get_logs(filter_params))  # type: ignore
