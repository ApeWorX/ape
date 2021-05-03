import os
from typing import Any

from web3 import HTTPProvider, Web3  # type: ignore
from web3.gas_strategies.rpc import rpc_gas_price_strategy

from ape.api import ProviderAPI, ReceiptAPI, TransactionAPI


class Infura(ProviderAPI):
    _web3: Web3 = None  # type: ignore

    def __post_init__(self):
        key = os.environ.get("WEB3_INFURA_PROJECT_ID") or os.environ.get("WEB3_INFURA_API_KEY")
        self._web3 = Web3(HTTPProvider(f"https://{self.network.name}.infura.io/v3/{key}"))
        self._web3.eth.set_gas_price_strategy(rpc_gas_price_strategy)

    def connect(self):
        pass

    def disconnect(self):
        pass

    def estimate_gas_cost(self, txn: TransactionAPI) -> int:
        return self._web3.eth.estimate_gas(txn.as_dict())

    @property
    def gas_price(self):
        return self._web3.eth.generate_gas_price()

    def get_nonce(self, address: str) -> int:
        return self._web3.eth.getTransactionCount(address)  # type: ignore

    def get_balance(self, address: str) -> int:
        return self._web3.eth.getBalance(address)  # type: ignore

    def get_code(self, address: str) -> bytes:
        return self._web3.eth.getCode(address)  # type: ignore

    def send_call(self, txn: TransactionAPI) -> Any:
        data = txn.encode()
        return self._web3.eth.call(data)

    def get_transaction(self, txn_hash: str) -> ReceiptAPI:
        # TODO: Work on API that let's you work with ReceiptAPI and re-send transactions
        receipt = self._web3.eth.wait_for_transaction_receipt(txn_hash)  # type: ignore
        txn = self._web3.eth.get_transaction(txn_hash)  # type: ignore
        return self.network.ecosystem.receipt_class.decode({**txn, **receipt})

    def send_transaction(self, txn: TransactionAPI) -> ReceiptAPI:
        txn_hash = self._web3.eth.send_raw_transaction(txn.encode())
        return self.get_transaction(txn_hash.hex())
