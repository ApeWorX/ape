from abc import ABCMeta, abstractmethod

from dataclassy import dataclass

from . import networks


@dataclass
class ExplorerAPI(metaclass=ABCMeta):
    """
    An Explorer must work with a particular Network in a particular Ecosystem
    """

    name: str  # Plugin name
    network: networks.NetworkAPI
    request_header: str

    @abstractmethod
    def get_address_url(self, address: str) -> str:
        ...

    @abstractmethod
    def get_transaction_url(self, transaction_hash: str) -> str:
        ...
