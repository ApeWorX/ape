import time
from typing import Callable, Dict, Iterator, List, Optional, Tuple, Union

import pandas as pd

from ape.api import BlockAPI, ReceiptAPI
from ape.api.address import BaseAddress
from ape.api.query import BlockQuery
from ape.exceptions import ChainError, UnknownSnapshotError
from ape.logging import logger
from ape.types import AddressType, BlockID, SnapshotID
from ape.utils import cached_property

from .base import BaseManager


class BlockContainer(BaseManager):
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
        if self.head.number is None:
            raise ChainError("Latest block has no number.")

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

        return self.range(len(self))

    def query(
        self,
        *columns: List[str],
        start_block: int = 0,
        stop_block: Optional[int] = None,
        engine_to_use: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        A method for querying blocks and returning a pandas DataFrame. If you
        do not provide a starting block, the 0 block is assumed. If you do not
        provide a stopping block, the last block is assumed. You can pass
        ``engine_to_use`` to short-circuit engine selection.

        Raises:
            :class:`~ape.exceptions.ChainError`: When ``stop_block`` is greater
              than the chain length.

        Args:
            columns (List[str]): columns in the DataFrame to return
            start_block (int): The first block, by number, to include in the
              query. Defaults to 0.
            stop_block (Optional[int]): The last block, by number, to include
              in the query. Defaults to the latest block.
            engine_to_use (Optional[str]): query engine to use, bypasses query
              engine selection algorithm.

        Returns:
            pandas.DataFrame
        """

        if stop_block is None:
            stop_block = self.height

        elif stop_block > self.height:
            raise ChainError(
                f"'stop_block={stop_block}' cannot be greater than the chain length ({len(self)}). "
                f"Use '{self.poll_blocks.__name__}()' to wait for future blocks."
            )

        query = BlockQuery(
            columns=columns,
            start_block=start_block,
            stop_block=stop_block,
            engine_to_use=engine_to_use,
        )

        return self.query_manager.query(query)

    def range(
        self, start_or_stop: int, stop: Optional[int] = None, step: int = 1
    ) -> Iterator[BlockAPI]:
        """
        Iterate over blocks. Works similarly to python ``range()``.

        Raises:
            :class:`~ape.exceptions.ChainError`: When ``stop`` is greater
                than the chain length.
            :class:`~ape.exceptions.ChainError`: When ``stop`` is less
                than ``start_block``.
            :class:`~ape.exceptions.ChainError`: When ``stop`` is less
                than 0.
            :class:`~ape.exceptions.ChainError`: When ``start`` is less
                than 0.

        Args:
            start_or_stop (int): When given just a single value, it is the stop.
              Otherwise, it is the start. This mimics the behavior of ``range``
              built-in Python function.
            stop (Optional[int]): The block number to stop before. Also the total
              number of blocks to get. If not setting a start value, is set by
              the first argument.
            step (Optional[int]): The value to increment by. Defaults to ``1``.
             number of blocks to get. Defaults to the latest block.

        Returns:
            Iterator[:class:`~ape.api.providers.BlockAPI`]
        """

        if stop is None:
            stop = start_or_stop
            start = 0
        else:
            start = start_or_stop

        if stop > len(self):
            raise ChainError(
                f"'stop={stop}' cannot be greater than the chain length ({len(self)}). "
                f"Use '{self.poll_blocks.__name__}()' to wait for future blocks."
            )
        elif stop < start:
            raise ValueError(f"stop '{stop}' cannot be less than start '{start}'.")
        elif stop < 0:
            raise ValueError(f"start '{start}' cannot be negative.")
        elif start_or_stop < 0:
            raise ValueError(f"stop '{stop}' cannot be negative.")

        # Note: the range `stop_block` is a non-inclusive stop, while the
        #       `.query` method uses an inclusive stop, so we must adjust downwards.
        results = self.query("*", start_block=start, stop_block=stop - 1)  # type: ignore
        for _, row in results.iterrows():
            yield self.provider.network.ecosystem.decode_block(dict(row.to_dict()))

    def poll_blocks(
        self,
        start: Optional[int] = None,
        stop: Optional[int] = None,
        required_confirmations: Optional[int] = None,
    ) -> Iterator[BlockAPI]:
        """
        Poll new blocks. Optionally set a start block to include historical blocks.
        **NOTE**: This is a daemon method; it does not terminate unless an exception occurrs
        or a ``stop`` is given.

        Usage example::

            from ape import chain

            for new_block in chain.blocks.poll_blocks():
                print(f"New block found: number={new_block.number}")

        Args:
            start (Optional[int]): The block number to start with. Defaults to the pending
              block number.
            stop (Optional[int]): Optionally set a future block number to stop at.
              Defaults to never-ending.
            required_confirmations (Optional[int]): The amount of confirmations to wait
              before yielding the block. The more confirmations, the less likely a reorg will occur.
              Defaults to the network's configured required confirmations.

        Returns:
            Iterator[:class:`~ape.api.providers.BlockAPI`]
        """
        if required_confirmations is None:
            required_confirmations = self.network_confirmations

        if stop is not None and stop <= self.chain_manager.blocks.height:
            raise ValueError("'stop' argument must be in the future.")

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

                    if stop and block.number == stop:
                        return

                has_yielded = True
                latest_confirmed_block_number = confirmable_block_number

            time.sleep(self.provider.network.block_time)

    def _get_block(self, block_id: BlockID) -> BlockAPI:
        return self.provider.get_block(block_id)


class AccountHistory(BaseManager):
    """
    A container mapping account addresses to the transaction from the active session.
    """

    _map: Dict[AddressType, List[ReceiptAPI]] = {}

    @cached_property
    def _convert(self) -> Callable:

        return self.conversion_manager.convert

    def __getitem__(self, address: Union[BaseAddress, AddressType, str]) -> List[ReceiptAPI]:
        """
        Get the list of transactions from the active session for the given address.

        Args:
            address (``AddressType``): The sender of the desired transactions.

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
            Iterator[Tuple[``AddressType``, :class:`~ape.api.providers.ReceiptAPI`]]
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


class ChainManager(BaseManager):
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
            blocks = BlockContainer()
            self._block_container_map[self.chain_id] = blocks

        return self._block_container_map[self.chain_id]

    @property
    def account_history(self) -> AccountHistory:
        """
        A mapping of transactions from the active session to the account responsible.
        """
        if self.chain_id not in self._account_history_map:
            history = AccountHistory()
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
    def pending_timestamp(self, new_value: str):
        self.provider.set_timestamp(self.conversion_manager.convert(value=new_value, type=int))

    def __repr__(self) -> str:
        props = f"id={self.chain_id}" if self.network_manager.active_provider else "disconnected"
        return f"<{self.__class__.__name__} ({props})>"

    def snapshot(self) -> SnapshotID:
        """
        Record the current state of the blockchain with intent to later
        call the method :meth:`~ape.managers.chain.ChainManager.revert`
        to go back to this point. This method is for local networks only.

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

    def mine(
        self,
        num_blocks: int = 1,
        timestamp: Optional[int] = None,
        deltatime: Optional[int] = None,
    ) -> None:
        """
        Mine any given number of blocks.

        Raises:
            ValueError: When a timestamp AND a deltatime argument are both passed

        Args:
            num_blocks (int): Choose the number of blocks to mine.
                Defaults to 1 block.
            timestamp (Optional[int]): Designate a time (in seconds) to begin mining.
                Defaults to None.
            deltatime (Optional[int]): Designate a change in time (in seconds) to begin mining.
                Defaults to None
        """
        if timestamp and deltatime:
            raise ValueError("Cannot give both `timestamp` and `deltatime` arguments together.")
        if timestamp:
            self.pending_timestamp = timestamp
        elif deltatime:
            self.pending_timestamp += deltatime
        self.provider.mine(num_blocks)
