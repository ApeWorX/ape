from typing import Dict, List, Optional, Union

from dataclassy import dataclass

from ape.api import AddressAPI, BlockAPI, ProviderAPI, TestProviderAPI, TransactionAPI
from ape.exceptions import ChainError, ProviderNotConnectedError, UnknownSnapshotError
from ape.types import AddressType, SnapshotID
from ape.utils import convert

from .networks import NetworkManager


@dataclass
class BlockContainer:
    """
    A list of blocks on the chain.

    Usages example::

        from ape import chain

        latest_block = chain.blocks[-1]

    """

    _provider: ProviderAPI

    def __getitem__(self, block_number: int) -> BlockAPI:
        """
        Get a block by number. Negative numbers start at the chain head and
        move backwards. For example, ``-1`` would be the latest block and
        ``-2`` would be the block prior to that one, and so on.

        Args:
            block_number (int): The number of the block to get.

        Returns:
            :class:`~ape.api.providers.BlockAPI`
        """
        if block_number < 0:
            latest_block = self._provider.get_block("latest").number
            block_number = latest_block + 1 + block_number

        return self._provider.get_block(block_number)

    def __len__(self) -> int:
        """
        The number of blocks in the chain.

        Returns:
            int
        """

        return self._provider.get_block("latest").number + 1


class AccountHistory:
    """
    A container mapping account addresses to the transaction from the active session.
    """

    _map: Dict[AddressType, List] = {}

    def __getitem__(self, address: Union[AddressAPI, AddressType, str]) -> List[TransactionAPI]:
        """
        Get the list of transactions from the active session for the given address.

        Args:
            address (:class:`~ape.types.AddressType`): The sender of the desired transactions.

        Returns:
            List[:class:`~ape.api.providers.TransactionAPI`]: The list of transactions. If there
            are no recorded transactions, returns the empty list.
        """
        address = convert(address, AddressType)
        return self._map.get(address, [])

    def append_transaction(self, txn: TransactionAPI):
        """
        Add a transaction to the stored list for the given account address.

        Raises:
            :class:`~ape.exceptions.ChainError`: When trying to append a transaction
              that is already in the list.

        Args:
            txn (:class:`~ape.api.providers.TransactionAPI`): The transaction to append.
              **NOTE**: The transaction is accessible in the list returned from container[sender].
        """
        address = convert(txn.sender, AddressType)
        if address not in self._map:
            self._map[address] = [txn]
            return

        if txn.hash in [t.hash for t in self._map[address]]:
            raise ChainError(f"Transaction '{txn.hash}' already known.")

        self._map[address].append(txn)


@dataclass
class ChainManager:
    """
    A class for managing the state of the active blockchain.
    Also handy for querying data about the chain and managing local caches.
    Access the chain manager singleton from the root ``ape`` namespace.

    Usage example::

        from ape import chain
    """

    _networks: NetworkManager
    _snapshots: List[SnapshotID] = []

    blocks: BlockContainer = None  # type: ignore
    """The list of blocks on the chain."""

    account_history: AccountHistory = AccountHistory()
    """A mapping of transactions from the active session to the account responsible."""

    def __post_init__(self):
        self.blocks = BlockContainer(self._networks.active_provider)

    @property
    def provider(self) -> ProviderAPI:
        """
        The active :class:`~ape.api.providers.ProviderAPI`.

        Raises:
            :class:`~ape.exceptions.ProviderNotConnectedError`: When not connected
              to a provider.
        """

        provider = self._networks.active_provider
        if not provider:
            raise ProviderNotConnectedError()

        return provider

    def snapshot(self) -> SnapshotID:
        """
        Record the current state of the blockchain with intent to later
        call the method :meth:`~ape.managers.chain.ChainManager.revert`
        to go back to this point. This method is for development networks
        only.

        Raises:
            NotImplementedError: When the active provider does not support
              snapshotting.

        Returns:
            :class:`~ape.types.SnapshotID`: The snapshot ID.
        """
        provider = self._get_test_provider(TestProviderAPI.snapshot.__name__)
        snapshot_id = provider.snapshot()

        if snapshot_id not in self._snapshots:
            self._snapshots.append(snapshot_id)

        return snapshot_id

    def restore(self, snapshot_id: Optional[SnapshotID] = None):
        """
        Regress the current call using the given snapshot ID.
        Allows developers to go back to a previous state.

        Raises:
            NotImplementedError: When the active provider does not support
              snapshotting.
            :class:`~ape.exceptions.UnknownSnapshotError`: When the snapshot ID is not cached.
            :class:`~ape.exceptions.ChainError`: When there are no snapshot IDs to select from.

        Args:
            snapshot_id (Optional[:class:`~ape.types.SnapshotID`]): The snapshot ID. Defaults
              to the most recent snapshot ID.
        """
        provider = self._get_test_provider(TestProviderAPI.revert.__name__)
        if not self._snapshots:
            raise ChainError("There are no snapshots to revert to.")
        elif snapshot_id is None:
            snapshot_id = self._snapshots.pop()
        elif snapshot_id not in self._snapshots:
            raise UnknownSnapshotError(snapshot_id)
        else:
            snapshot_index = self._snapshots.index(snapshot_id)
            self._snapshots = self._snapshots[:snapshot_index]

        provider.revert(snapshot_id)

    def _get_test_provider(self, method_name: str) -> TestProviderAPI:
        provider = self.provider
        if not isinstance(provider, TestProviderAPI):
            raise NotImplementedError(
                f"Provider '{provider.name}' does not support method '{method_name}'."
            )

        return provider
