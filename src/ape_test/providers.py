from web3 import EthereumTesterProvider, Web3  # type: ignore

from ape.api import ProviderAPI


class LocalNetwork(Web3, ProviderAPI):
    _web3: Web3 = None  # type: ignore

    def __init__(self):
        self._web3 = Web3(EthereumTesterProvider())

    def transfer_cost(self, address: str) -> int:
        if self.get_code(address) == b"":
            return 21000
        else:
            raise

    @property
    def gas_price(self):
        return 0

    def get_nonce(self, address: str) -> int:
        return self._web3.eth.getTransactionCount(address)  # type: ignore

    def get_balance(self, address: str) -> int:
        return self._web3.eth.getBalance(address)  # type: ignore

    def get_code(self, address: str) -> bytes:
        return self._web3.eth.getCode(address)  # type: ignore

    def send_transaction(self, data: bytes) -> bytes:
        return self._web3.eth.sendRawTransaction(data)  # type: ignore
