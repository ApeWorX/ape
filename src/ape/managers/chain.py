import time
from typing import Dict, Iterator, List, Optional, Union

from dataclassy import dataclass

from ape.api import AddressAPI, BlockAPI, ProviderAPI, ReceiptAPI, TestProviderAPI
from ape.exceptions import ChainError, ProviderNotConnectedError, UnknownSnapshotError
from ape.logging import logger
from ape.types import AddressType, BlockID, SnapshotID

from .networks import NetworkManager


@dataclass
class BlockContainer:
    """
    A list of blocks on the chain.

    Usages example::

        from ape import chain

        latest_block = chain.blocks[-1]

    """

    networks: NetworkManager
    _poll_wait_interval = 2  # Seconds

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
            block_number = self.height + 1 + block_number

        return self._get_block(block_number)

    def __len__(self) -> int:
        """
        The number of blocks in the chain.

        Returns:
            int
        """

        return self.height + 1

    def __iter__(self) -> Iterator[BlockAPI]:
        """
        Iterate over all the current blocks.

        Returns:
            Iterator[:class:`~ape.api.providers.BlockAPI`]
        """

        return self.range()

    @property
    def head(self) -> BlockAPI:
        """
        The latest block.
        """

        return self._get_block("latest")

    @property
    def height(self) -> int:
        """
        The latest block number.
        """

        return self.head.number

    @property
    def _provider(self) -> ProviderAPI:
        if not self.networks.active_provider:
            raise ProviderNotConnectedError()

        return self.networks.active_provider

    @property
    def _network_confirmations(self) -> int:
        return self._provider.network.required_confirmations

    def range(self, start: int = 0, stop: Optional[int] = None) -> Iterator[BlockAPI]:
        """
        Iterate over blocks. Works similarly to python ``range()``.

        Args:
            start (int): The first block, by number, to include in the range.
              Defaults to 0.
            stop (Optional[int]): The block number to stop before. Also the total
             number of blocks to get.

        Returns:
            Iterator[:class:`~ape.api.providers.BlockAPI`]
        """

        if stop is None:
            stop = len(self)

        for i in range(start, stop):
            yield self._get_block(i)

    def poll_blocks(
        self, start: Optional[int] = None, required_confirmations: Optional[int] = None
    ) -> Iterator[BlockAPI]:
        """
        Poll new blocks. Optionally set a start block to include historical blocks.
        **NOTE**: This is a deamon method; it does not terminate.

        Args:
            start (Optional[int]): The block number to start with. Defaults to the block
              of the ``+1`` the current block number.
            required_confirmations (Optional[int]): The amount of confirmations to wait
              before yielding the block.

        Returns:
            Iterator[:class:`~ape.api.providers.BlockAPI`]
        """
        if required_confirmations is None:
            required_confirmations = self._network_confirmations

        # Get number of last block with the necessary amount of confirmations.
        latest_confirmed_block_number = self.height - required_confirmations

        if start is not None:
            # Front-load historically confirmed blocks.
            yield from self.range(start, latest_confirmed_block_number + 1)

        time.sleep(self._poll_wait_interval)

        while True:
            confirmable_block_number = self.height - latest_confirmed_block_number
            if confirmable_block_number < latest_confirmed_block_number:
                logger.error(
                    "Chain has reorganized since returning the last block. "
                    "Try adjusting the required network confirmations."
                )
            elif confirmable_block_number > latest_confirmed_block_number:
                yield self._get_block(confirmable_block_number)
                latest_confirmed_block_number = confirmable_block_number

            time.sleep(self._poll_wait_interval)

    def _get_block(self, block_id: BlockID) -> BlockAPI:
        return self._provider.get_block(block_id)


class AccountHistory:
    """
    A container mapping account addresses to the transaction from the active session.
    """

    _map: Dict[AddressType, List[ReceiptAPI]] = {}

    def __getitem__(self, address: Union[AddressAPI, AddressType, str]) -> List[ReceiptAPI]:
        """
        Get the list of transactions from the active session for the given address.

        Args:
            address (:class:`~ape.types.AddressType`): The sender of the desired transactions.

        Returns:
            List[:class:`~ape.api.providers.TransactionAPI`]: The list of transactions. If there
            are no recorded transactions, returns the empty list.
        """
        address_key: AddressType = _convert(address, AddressType)
        return self._map.get(address_key, [])

    def append(self, txn_receipt: ReceiptAPI):
        """
        Add a transaction to the stored list for the given account address.

        Raises:
            :class:`~ape.exceptions.ChainError`: When trying to append a transaction
              that is already in the list.

        Args:
            txn_receipt (:class:`~ape.api.providers.ReceiptAPI`): The transaction receipt to append.
              **NOTE**: The receipt is accessible in the list returned from container[sender].
        """
        address = _convert(txn_receipt.sender, AddressType)
        if address not in self._map:
            self._map[address] = [txn_receipt]
            return

        if txn_receipt.txn_hash in [r.txn_hash for r in self._map[address]]:
            raise ChainError(f"Transaction '{txn_receipt.txn_hash}' already known.")

        self._map[address].append(txn_receipt)


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
    _time_offset: int = 0
    _chain_id_map: Dict[str, int] = {}

    account_history: AccountHistory = AccountHistory()
    """A mapping of transactions from the active session to the account responsible."""

    def __repr__(self) -> str:
        try:
            return f"<ChainManager (chain_id={self.chain_id})>"
        except ProviderNotConnectedError:
            return "<ChainManager (disconnected)>"

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

    @property
    def blocks(self) -> BlockContainer:
        """
        The list of blocks on the chain.
        """
        return BlockContainer(self._networks)  # type: ignore

    @property
    def chain_id(self) -> int:
        """
        The blockchain ID.
        See `ChainList <https://chainlist.org/>`__ for a comprehensive list of IDs.
        """

        network_name = self.provider.network.name
        if network_name not in self._chain_id_map:
            self._chain_id_map[network_name] = self.provider.chain_id

        return self._chain_id_map[network_name]

    @property
    def gas_price(self) -> int:
        """
        The price for what it costs to transact
        (pre-`EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__).
        """

        return self.provider.gas_price

    @property
    def base_fee(self) -> int:
        """
        The minimum value required to get your transaction
        included on the next block.
        Only providers that implement `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__
        will use this property.

        Raises:
            NotImplementedError: When this provider does not implement
              `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__.
        """

        return self.provider.base_fee

    @property
    def pending_timestamp(self) -> int:
        """
        The current epoch time of the chain, as an ``int``.
        """

        return int(time.time() + self._time_offset)

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


def _convert(*args, **kwargs):
    from ape import convert

    return convert(*args, **kwargs)
