from typing import List, Optional

from dataclassy import dataclass

from ape.api import ProviderAPI, TestProviderAPI
from ape.exceptions import ChainError, ProviderNotConnectedError
from ape.types import SnapshotID

from .networks import NetworkManager


@dataclass
class ChainManager:
    """
    A manager for controlling and manipulating development blockchains
    and querying chain-data.
    """

    _networks: NetworkManager
    _snapshots: List[SnapshotID] = []

    @property
    def provider(self) -> ProviderAPI:
        provider = self._networks.active_provider
        if not provider:
            raise ProviderNotConnectedError()

        return provider

    @property
    def block_number(self) -> int:
        return self.provider.get_block("latest").number

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
        provider = self._get_test_provider()
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
            ChainError: When the snapshot ID does not exist or there are
              no snapshot IDs to select from.

        Args:
            snapshot_id (Optional[:class:`~ape.types.SnapshotID`]): The snapshot ID. Defaults
            to the most recent snapshot ID.
        """
        provider = self._get_test_provider()
        if not self._snapshots:
            raise ChainError("There are no snapshots to revert to.")
        elif snapshot_id is None:
            snapshot_id = self._snapshots.pop()
        elif snapshot_id not in self._snapshots:
            raise ChainError(f"Unknown snapshot_id '{snapshot_id}'.")
        else:
            snapshot_index = self._snapshots.index(snapshot_id)
            self._snapshots = self._snapshots[:snapshot_index]

        provider.revert(snapshot_id)

    def _get_test_provider(self) -> TestProviderAPI:
        provider = self.provider
        if not isinstance(provider, TestProviderAPI):
            raise NotImplementedError(f"Provider '{provider.name}' does not support snapshotting.")

        return provider
