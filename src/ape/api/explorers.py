from typing import Iterator, Optional

from ethpm_types import ContractType

from ape.types import AddressType
from ape.utils import abstractdataclass, abstractmethod

from . import networks
from .providers import ReceiptAPI


@abstractdataclass
class ExplorerAPI:
    """
    An API class representing a blockchain explorer for a particular network
    in a particular ecosystem.
    """

    name: str  # Plugin name
    network: networks.NetworkAPI
    request_header: str

    @abstractmethod
    def get_address_url(self, address: AddressType) -> str:
        """
        Get an address URL, such as for a transaction.

        Args:
            address (:class:`~ape.types.AddressType`): The address to
              get the URL for.

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
            address (:class:`~ape.types.AddressType`): The contract address.

        Returns:
            Optional[``ContractType``]: If not published, returns ``None``.
        """

    @abstractmethod
    def get_account_transactions(self, address: AddressType) -> Iterator[ReceiptAPI]:
        """
        Get a list of list of transactions performed by an address.

        Args:
            address (:class:`~ape.types.AddressType`): The account address.

        Returns:
            Iterator[:class:`~ape.api.providers.ReceiptAPI`]
        """
