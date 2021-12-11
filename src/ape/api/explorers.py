from . import networks
from .base import abstractdataclass, abstractmethod


@abstractdataclass
class ExplorerAPI:
    """
    An Explorer must work with a particular Network in a particular Ecosystem
    """

    name: str  # Plugin name
    network: networks.NetworkAPI
    request_header: str

    @abstractmethod
    def get_address_url(self, address: str) -> str:
        """
        Get the address URL for the given address.

        Args:
            address (`str`): Value of address

        Returns:
            str
        """

    @abstractmethod
    def get_transaction_url(self, transaction_hash: str) -> str:
        """
        Get the transaction URL for the given transaction.

        Args:
            transaction_hash (str): The transaction hash.

        Returns:
            str
        """
