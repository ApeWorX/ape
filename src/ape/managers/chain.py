from typing import List, Optional

from dataclassy import dataclass

from ape.api import BlockAPI, ProviderAPI, TestProviderAPI
from ape.exceptions import ChainError, ProviderNotConnectedError, UnknownSnapshotError
from ape.types import SnapshotID

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

        return self._provider.get_block("latest").number


@dataclass
class ChainManager:
    """
    A class for managing the state of the active blockchain.
    Also handy for querying data about the chain and managing local caches.
    Access the chain manager singleton from the root ``ape`` namespace.

    Usage example::

        from ape import  chain
    """

    _networks: NetworkManager
    _snapshots: List[SnapshotID] = []

    blocks: BlockContainer = None  # type: ignore
    """The list of blocks on the chain."""

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
        provider = self._get_test_provider("snapshot")
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
        provider = self._get_test_provider("restore")
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
