from web3 import EthereumTesterProvider, Web3  # type: ignore

from ape.api import ProviderAPI


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

    def transfer_cost(self, address: str) -> int:
        if self.get_code(address) == b"":
            return 21000
        else:
            raise

    @property
    def gas_price(self):
        return 0

    def get_nonce(self, address: str) -> int:
        return self._web3.eth.get_transaction_count(address)  # type: ignore

    def get_balance(self, address: str) -> int:
        return self._web3.eth.get_balance(address)  # type: ignore

    def get_code(self, address: str) -> bytes:
        return self._web3.eth.get_code(address)  # type: ignore

    def send_transaction(self, data: bytes) -> bytes:
        return self._web3.eth.send_raw_transaction(data)  # type: ignore
