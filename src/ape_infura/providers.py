import os

from web3 import HTTPProvider, Web3  # type: ignore
from web3.gas_strategies.rpc import rpc_gas_price_strategy

from ape.api import ProviderAPI


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

    def transfer_cost(self, address: str) -> int:
        if self.get_code(address) == b"":
            return 21000
        else:
            raise

    @property
    def gas_price(self):
        return self._web3.eth.generate_gas_price()

    def get_nonce(self, address: str) -> int:
        return self._web3.eth.getTransactionCount(address)  # type: ignore

    def get_balance(self, address: str) -> int:
        return self._web3.eth.getBalance(address)  # type: ignore

    def get_code(self, address: str) -> bytes:
        return self._web3.eth.getCode(address)  # type: ignore

    def send_transaction(self, data: bytes) -> bytes:
        return self._web3.eth.sendRawTransaction(data)  # type: ignore
