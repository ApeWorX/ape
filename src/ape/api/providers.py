from abc import ABCMeta, abstractmethod
from pathlib import Path

from dataclassy import dataclass

from . import networks


@dataclass
class ProviderAPI(metaclass=ABCMeta):
    """
    A Provider must work with a particular Network in a particular Ecosystem
    """

    name: str  # Plugin name
    network: networks.NetworkAPI
    config: dict
    data_folder: Path
    request_header: str

    @abstractmethod
    def connect(self):
        ...

    @abstractmethod
    def disconnect(self):
        ...

    @abstractmethod
    def update_settings(self, new_settings: dict):
        ...

    @abstractmethod
    def get_balance(self, address: str) -> int:
        ...

    @abstractmethod
    def get_code(self, address: str) -> bytes:
        ...

    @abstractmethod
    def get_nonce(self, address: str) -> int:
        ...

    @abstractmethod
    def transfer_cost(self, address: str) -> int:
        ...

    @property
    @abstractmethod
    def gas_price(self):
        ...

    @abstractmethod
    def send_transaction(self, data: bytes) -> bytes:
        ...
