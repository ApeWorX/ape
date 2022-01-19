import time
from typing import Callable, Dict, Iterator, List, Optional, Tuple, Union

from dataclassy import dataclass

from ape.api import AddressAPI, BlockAPI, ProviderAPI, ReceiptAPI
from ape.exceptions import ChainError, ProviderNotConnectedError, UnknownSnapshotError
from ape.logging import logger
from ape.types import AddressType, BlockID, SnapshotID
from ape.utils import cached_property

from .networks import NetworkManager


@dataclass
class _ConnectedChain:
    _networks: NetworkManager

    @property
    def provider(self) -> ProviderAPI:
        if not self._networks.active_provider:
            raise ProviderNotConnectedError()

        return self._networks.active_provider


class BlockContainer(_ConnectedChain):
    """
    A list of blocks on the chain.

    Usages example::

        from ape import chain

        latest_block = chain.blocks[-1]

    """

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
    def network_confirmations(self) -> int:
        return self.provider.network.required_confirmations

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
            block_number = len(self) + block_number

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

        if stop > len(self):
            raise ChainError(
                f"'stop={stop}' cannot be greater than the chain length ({len(self)}). "
                f"Use '{self.poll_blocks.__name__}()' to wait for future blocks."
            )
        elif stop < start:
            raise ValueError(f"stop '{stop}' cannot be less than start '{start}'.")
        elif stop < 0:
            raise ValueError(f"start '{start}' cannot be negative.")
        elif start < 0:
            raise ValueError(f"stop '{stop}' cannot be negative.")

        for i in range(start, stop):
            yield self._get_block(i)

    def poll_blocks(
        self,
        start: Optional[int] = None,
        required_confirmations: Optional[int] = None,
    ) -> Iterator[BlockAPI]:
        """
        Poll new blocks. Optionally set a start block to include historical blocks.
        **NOTE**: This is a daemon method; it does not terminate unless an exception occurrs.

        Usage example::

            from ape import chain

            for new_block in chain.blocks.poll_blocks():
                print(f"New block found: number={new_block.number}")

        Args:
            start (Optional[int]): The block number to start with. Defaults to the pending
              block number.
            required_confirmations (Optional[int]): The amount of confirmations to wait
              before yielding the block. The more confirmations, the less likely a reorg
                will occur.

        Returns:
            Iterator[:class:`~ape.api.providers.BlockAPI`]
        """
        if required_confirmations is None:
            required_confirmations = self.network_confirmations

        # Get number of last block with the necessary amount of confirmations.
        latest_confirmed_block_number = self.height - required_confirmations
        has_yielded = False

        if start is not None:
            # Front-load historically confirmed blocks.
            yield from self.range(start, latest_confirmed_block_number + 1)
            has_yielded = True

        time.sleep(self.provider.network.block_time)

        while True:
            confirmable_block_number = self.height - required_confirmations
            if confirmable_block_number < latest_confirmed_block_number and has_yielded:
                logger.error(
                    "Chain has reorganized since returning the last block. "
                    "Try adjusting the required network confirmations."
                )
            elif confirmable_block_number > latest_confirmed_block_number:
                # Yield all missed confirmable blocks
                new_blocks_count = confirmable_block_number - latest_confirmed_block_number
                for i in range(new_blocks_count):
                    block_num = latest_confirmed_block_number + i
                    block = self._get_block(block_num)
                    yield block

                has_yielded = True
                latest_confirmed_block_number = confirmable_block_number

            time.sleep(self.provider.network.block_time)

    def _get_block(self, block_id: BlockID) -> BlockAPI:
        return self.provider.get_block(block_id)


class AccountHistory(_ConnectedChain):
    """
    A container mapping account addresses to the transaction from the active session.
    """

    _map: Dict[AddressType, List[ReceiptAPI]] = {}

    @cached_property
    def _convert(self) -> Callable:
        from ape import convert

        return convert

    def __getitem__(self, address: Union[AddressAPI, AddressType, str]) -> List[ReceiptAPI]:
        """
        Get the list of transactions from the active session for the given address.

        Args:
            address (:class:`~ape.types.AddressType`): The sender of the desired transactions.

        Returns:
            List[:class:`~ape.api.providers.TransactionAPI`]: The list of transactions. If there
            are no recorded transactions, returns an empty list.
        """

        address_key: AddressType = self._convert(address, AddressType)
        explorer = self.provider.network.explorer
        explorer_receipts = (
            [r for r in explorer.get_account_transactions(address_key)] if explorer else []
        )
        for receipt in explorer_receipts:
            if receipt.txn_hash not in [r.txn_hash for r in self._map.get(address_key, [])]:
                self.append(receipt)

        return self._map.get(address_key, [])

    def __iter__(self) -> Iterator[AddressType]:
        """
        Iterate through the accounts listed in the history map.

        Returns:
            List[str]
        """

        yield from self._map

    def items(self) -> Iterator[Tuple[AddressType, List[ReceiptAPI]]]:
        """
        Iterate through the list of address-types to list of transaction receipts.

        Returns:
            Iterator[Tuple[:class:`~ape.types.AddressType`, :class:`~ape.api.providers.ReceiptAPI`]]
        """
        yield from self._map.items()

    def append(self, txn_receipt: ReceiptAPI):
        """
        Add a transaction to the stored list for the given account address.

        Raises:
            :class:`~ape.exceptions.ChainError`: When trying to append a transaction
              receipt that is already in the list.

        Args:
            txn_receipt (:class:`~ape.api.providers.ReceiptAPI`): The transaction receipt to append.
              **NOTE**: The receipt is accessible in the list returned from
              :meth:`~ape.managers.chain.AccountHistory.__getitem__`.
        """
        address = self._convert(txn_receipt.sender, AddressType)
        if address not in self._map:
            self._map[address] = [txn_receipt]
            return

        if txn_receipt.txn_hash in [r.txn_hash for r in self._map[address]]:
            raise ChainError(f"Transaction '{txn_receipt.txn_hash}' already known.")

        self._map[address].append(txn_receipt)

    def revert_to_block(self, block_number: int):
        """
        Remove all receipts past the given block number.

        Args:
            block_number (int): The block number to revert to.
        """

        self._map = {
            a: [r for r in receipts if r.block_number <= block_number]
            for a, receipts in self.items()
        }


class ChainManager(_ConnectedChain):
    """
    A class for managing the state of the active blockchain.
    Also handy for querying data about the chain and managing local caches.
    Access the chain manager singleton from the root ``ape`` namespace.

    Usage example::

        from ape import chain
    """

    _snapshots: List[SnapshotID] = []
    _chain_id_map: Dict[str, int] = {}
    _block_container_map: Dict[int, BlockContainer] = {}
    _account_history_map: Dict[int, AccountHistory] = {}

    @property
    def blocks(self) -> BlockContainer:
        """
        The list of blocks on the chain.
        """
        if self.chain_id not in self._block_container_map:
            blocks = BlockContainer(self._networks)  # type: ignore
            self._block_container_map[self.chain_id] = blocks

        return self._block_container_map[self.chain_id]

    @property
    def account_history(self) -> AccountHistory:
        """
        A mapping of transactions from the active session to the account responsible.
        """
        if self.chain_id not in self._account_history_map:
            history = AccountHistory(self._networks)  # type: ignore
            self._account_history_map[self.chain_id] = history

        return self._account_history_map[self.chain_id]

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
        The price for what it costs to transact.
        """

        return self.provider.gas_price

    @property
    def base_fee(self) -> int:
        """
        The minimum value required to get your transaction included on the next block.
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
        You can also set the timestamp for development purposes.

        Usage example::

            from ape import chain

            chain.pending_timestamp += 3600
        """

        return self.provider.get_block("pending").timestamp

    @pending_timestamp.setter
    def pending_timestamp(self, new_value: int):
        self.provider.set_timestamp(new_value)

    def __repr__(self) -> str:
        props = f"id={self.chain_id}" if self._networks.active_provider else "disconnected"
        return f"<ChainManager ({props})>"

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
        snapshot_id = self.provider.snapshot()

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
        if not self._snapshots:
            raise ChainError("There are no snapshots to revert to.")
        elif snapshot_id is None:
            snapshot_id = self._snapshots.pop()
        elif snapshot_id not in self._snapshots:
            raise UnknownSnapshotError(snapshot_id)
        else:
            snapshot_index = self._snapshots.index(snapshot_id)
            self._snapshots = self._snapshots[:snapshot_index]

        self.provider.revert(snapshot_id)
        self.account_history.revert_to_block(self.blocks.height)

    def mine(self, num_blocks: int = 1, timestamp: Optional[int] = None) -> None:
        if timestamp:
            self.pending_timestamp = timestamp
        self.provider.mine(num_blocks)
