from typing import TYPE_CHECKING, Iterator, Optional

from ethpm_types import ContractType

from ape.api import networks
from ape.types import AddressType
from ape.utils import BaseInterfaceModel, abstractmethod

if TYPE_CHECKING:
    from ape.api.transactions import ReceiptAPI


class ExplorerAPI(BaseInterfaceModel):
    """
    An API class representing a blockchain explorer for a particular network
    in a particular ecosystem.
    """

    name: str  # Plugin name
    network: networks.NetworkAPI

    @abstractmethod
    def get_address_url(self, address: AddressType) -> str:
        """
        Get an address URL, such as for a transaction.

        Args:
            address (``AddressType``): The address to get the URL for.

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

    @abstractmethod
    def get_contract_type(self, address: AddressType) -> Optional[ContractType]:
        """
        Get the contract type for a given address if it has been published in an explorer.

        Args:
            address (``AddressType``): The contract address.

        Returns:
            Optional[``ContractType``]: If not published, returns ``None``.
        """

    @abstractmethod
    def get_account_transactions(self, address: AddressType) -> Iterator["ReceiptAPI"]:
        """
        Get a list of list of transactions performed by an address.

        Args:
            address (``AddressType``): The account address.

        Returns:
            Iterator[:class:`~ape.api.providers.ReceiptAPI`]
        """
