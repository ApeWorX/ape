from typing import Optional

from ethpm_types import ContractType

from ape.api import networks
from ape.types import AddressType
from ape.utils import BaseInterfaceModel, abstractmethod


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
            address (:class:`~ape.types.address.AddressType`): The address.

        Returns:
            str: The URL.
        """

    @abstractmethod
    def get_transaction_url(self, transaction_hash: str) -> str:
        """
        Get the transaction URL for the given transaction.

        Args:
            transaction_hash (str): The transaction hash.

        Returns:
            str: The URL.
        """

    @abstractmethod
    def get_contract_type(self, address: AddressType) -> Optional[ContractType]:
        """
        Get the contract type for a given address if it has been published to this explorer.

        Args:
            address (:class:`~ape.types.address.AddressType`): The contract address.

        Returns:
            Optional[``ContractType``]: If not published, returns ``None``.
        """

    @abstractmethod
    def publish_contract(self, address: AddressType):
        """
        Publish a contract to the explorer.

        Args:
            address (:class:`~ape.types.address.AddressType`): The address of the deployed contract.
        """
