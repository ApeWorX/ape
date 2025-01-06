from collections import defaultdict
from collections.abc import Iterator
from contextlib import contextmanager
from functools import cached_property, partial, singledispatchmethod
from statistics import mean, median
from typing import IO, TYPE_CHECKING, Optional, Union, cast

import pandas as pd
from rich.box import SIMPLE
from rich.table import Table

from ape.api.address import BaseAddress
from ape.api.providers import BlockAPI
from ape.api.query import (
    AccountTransactionQuery,
    BlockQuery,
    extract_fields,
    validate_and_expand_columns,
)
from ape.api.transactions import ReceiptAPI
from ape.exceptions import (
    APINotImplementedError,
    BlockNotFoundError,
    ChainError,
    ProviderNotConnectedError,
    QueryEngineError,
    TransactionNotFoundError,
    UnknownSnapshotError,
)
from ape.logging import get_rich_console, logger
from ape.managers._contractscache import ContractCache
from ape.managers.base import BaseManager
from ape.types.address import AddressType
from ape.utils.basemodel import BaseInterfaceModel
from ape.utils.misc import ZERO_ADDRESS, is_evm_precompile, is_zero_hex, log_instead_of_fail

if TYPE_CHECKING:
    from rich.console import Console as RichConsole

    from ape.types.trace import GasReport, SourceTraceback
    from ape.types.vm import SnapshotID


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
        return self.provider.get_block("latest")

    @property
    def height(self) -> int:
        """
        The latest block number.
        """
        try:
            head = self.head
        except BlockNotFoundError:
            return 0

        if head.number is None:
            raise ChainError("Latest block has no number.")

        return head.number

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

        return self.provider.get_block(block_number)

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
        *columns: str,
        start_block: int = 0,
        stop_block: Optional[int] = None,
        step: int = 1,
        engine_to_use: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        A method for querying blocks and returning an Iterator. If you
        do not provide a starting block, the 0 block is assumed. If you do not
        provide a stopping block, the last block is assumed. You can pass
        ``engine_to_use`` to short-circuit engine selection.

        Raises:
            :class:`~ape.exceptions.ChainError`: When ``stop_block`` is greater
              than the chain length.

        Args:
            *columns (str): columns in the DataFrame to return
            start_block (int): The first block, by number, to include in the
              query. Defaults to 0.
            stop_block (Optional[int]): The last block, by number, to include
              in the query. Defaults to the latest block.
            step (int): The number of blocks to iterate between block numbers.
              Defaults to ``1``.
            engine_to_use (Optional[str]): query engine to use, bypasses query
              engine selection algorithm.

        Returns:
            pd.DataFrame
        """

        if start_block < 0:
            start_block = len(self) + start_block

        if stop_block is None:
            stop_block = self.height

        elif stop_block < 0:
            stop_block = len(self) + stop_block

        elif stop_block > len(self):
            raise ChainError(
                f"'stop={stop_block}' cannot be greater than the chain length ({self.height})."
            )

        query = BlockQuery(
            columns=list(columns),
            start_block=start_block,
            stop_block=stop_block,
            step=step,
        )

        blocks = self.query_manager.query(query, engine_to_use=engine_to_use)
        columns: list[str] = validate_and_expand_columns(  # type: ignore
            columns, self.head.__class__
        )
        extraction = partial(extract_fields, columns=columns)
        data = map(lambda b: extraction(b), blocks)
        return pd.DataFrame(columns=columns, data=data)

    def range(
        self,
        start_or_stop: int,
        stop: Optional[int] = None,
        step: int = 1,
        engine_to_use: Optional[str] = None,
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
            engine_to_use (Optional[str]): query engine to use, bypasses query
              engine selection algorithm.

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

        # Note: the range `stop_block` is a non-inclusive stop, while the
        #       `.query` method uses an inclusive stop, so we must adjust downwards.
        query = BlockQuery(
            columns=list(self.head.model_fields),  # TODO: fetch the block fields from EcosystemAPI
            start_block=start,
            stop_block=stop - 1,
            step=step,
        )

        blocks = self.query_manager.query(query, engine_to_use=engine_to_use)
        yield from cast(Iterator[BlockAPI], blocks)

    def poll_blocks(
        self,
        start_block: Optional[int] = None,
        stop_block: Optional[int] = None,
        required_confirmations: Optional[int] = None,
        new_block_timeout: Optional[int] = None,
    ) -> Iterator[BlockAPI]:
        """
        Poll new blocks. Optionally set a start block to include historical blocks.

        **NOTE**: When a chain reorganization occurs, this method logs an error and
        yields the missed blocks, even if they were previously yielded with different
        block numbers.

        **NOTE**: This is a daemon method; it does not terminate unless an exception occurs
        or a ``stop_block`` is given.

        Usage example::

            from ape import chain

            for new_block in chain.blocks.poll_blocks():
                print(f"New block found: number={new_block.number}")

        Args:
            start_block (Optional[int]): The block number to start with. Defaults to the pending
              block number.
            stop_block (Optional[int]): Optionally set a future block number to stop at.
              Defaults to never-ending.
            required_confirmations (Optional[int]): The amount of confirmations to wait
              before yielding the block. The more confirmations, the less likely a reorg will occur.
              Defaults to the network's configured required confirmations.
            new_block_timeout (Optional[float]): The amount of time to wait for a new block before
              timing out. Defaults to 10 seconds for local networks or ``50 * block_time`` for live
              networks.

        Returns:
            Iterator[:class:`~ape.api.providers.BlockAPI`]
        """

        if required_confirmations is None:
            required_confirmations = self.network_confirmations

        if stop_block is not None and stop_block <= self.chain_manager.blocks.height:
            raise ValueError("'stop' argument must be in the future.")

        # Get number of last block with the necessary amount of confirmations.
        block = None

        head_minus_confirms = self.height - required_confirmations
        if start_block is not None and start_block <= head_minus_confirms:
            # Front-load historical blocks.
            for block in self.range(start_block, head_minus_confirms + 1):
                yield block

        yield from self.provider.poll_blocks(
            stop_block=stop_block,
            required_confirmations=required_confirmations,
            new_block_timeout=new_block_timeout,
        )


class AccountHistory(BaseInterfaceModel):
    """
    A container mapping account addresses to the transaction from the active session.
    """

    address: AddressType
    """
    The address to get history for.
    """

    sessional: list[ReceiptAPI] = []
    """
    The receipts from the current Python session.
    """

    @property
    def outgoing(self) -> Iterator[ReceiptAPI]:
        """
        All outgoing transactions, from earliest to latest.
        """

        start_nonce = 0
        stop_nonce = len(self) - 1  # just to cache this value

        # TODO: Add ephemeral network sessional history to `ape-cache` instead,
        #       and remove this (replace with `yield from iter(self[:len(self)])`)
        for receipt in self.sessional:
            if receipt.nonce is None:
                # Not an on-chain receipt? idk - has only seen as anomaly in tests.
                continue

            elif receipt.nonce < start_nonce:
                raise QueryEngineError("Sessional history corrupted")

            elif receipt.nonce > start_nonce:
                # NOTE: There's a gap in our sessional history, so fetch from query engine
                yield from iter(self[start_nonce : receipt.nonce + 1])  # noqa: E203

            yield receipt
            start_nonce = receipt.nonce + 1  # start next loop on the next item

        if start_nonce != stop_nonce:
            # NOTE: there is no more session history, so just return query engine iterator
            yield from iter(self[start_nonce : stop_nonce + 1])  # noqa: E203

    def query(
        self,
        *columns: str,
        start_nonce: int = 0,
        stop_nonce: Optional[int] = None,
        engine_to_use: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        A method for querying transactions made by an account and returning an Iterator.
        If you do not provide a starting nonce, the first transaction is assumed.
        If you do not provide a stopping block, the last transaction is assumed.
        You can pass ``engine_to_use`` to short-circuit engine selection.

        Raises:
            :class:`~ape.exceptions.ChainError`: When ``stop_nonce`` is greater
              than the account's current nonce.

        Args:
            *columns (str): columns in the DataFrame to return
            start_nonce (int): The first transaction, by nonce, to include in the
              query. Defaults to 0.
            stop_nonce (Optional[int]): The last transaction, by nonce, to include
              in the query. Defaults to the latest transaction.
            engine_to_use (Optional[str]): query engine to use, bypasses query
              engine selection algorithm.

        Returns:
            pd.DataFrame
        """

        if start_nonce < 0:
            start_nonce = len(self) + start_nonce

        if stop_nonce is None:
            stop_nonce = len(self)

        elif stop_nonce < 0:
            stop_nonce = len(self) + stop_nonce

        elif stop_nonce > len(self):
            raise ChainError(
                f"'stop={stop_nonce}' cannot be greater than account's current nonce ({len(self)})."
            )

        query = AccountTransactionQuery(
            columns=list(columns),
            account=self.address,
            start_nonce=start_nonce,
            stop_nonce=stop_nonce,
        )

        txns = self.query_manager.query(query, engine_to_use=engine_to_use)
        columns = validate_and_expand_columns(columns, ReceiptAPI)  # type: ignore
        extraction = partial(extract_fields, columns=columns)
        data = map(lambda tx: extraction(tx), txns)
        return pd.DataFrame(columns=columns, data=data)

    def __iter__(self) -> Iterator[ReceiptAPI]:  # type: ignore[override]
        yield from self.outgoing

    def __len__(self) -> int:
        """
        The transaction count of the address.
        """

        return self.provider.get_nonce(self.address)

    @singledispatchmethod
    def __getitem__(self, index):
        raise IndexError(f"Can't handle type {type(index)}")

    @__getitem__.register
    def __getitem_int(self, index: int) -> ReceiptAPI:
        if index < 0:
            index += len(self)

        try:
            return cast(
                ReceiptAPI,
                next(
                    self.query_manager.query(
                        AccountTransactionQuery(
                            columns=list(ReceiptAPI.__pydantic_fields__),
                            account=self.address,
                            start_nonce=index,
                            stop_nonce=index,
                        )
                    )
                ),
            )
        except StopIteration as e:
            raise IndexError(f"index {index} out of range") from e

    @__getitem__.register
    def __getitem_slice(self, indices: slice) -> list[ReceiptAPI]:
        start, stop, step = (
            indices.start or 0,
            indices.stop or len(self),
            indices.step or 1,
        )

        if start < 0:
            start += len(self)

        if stop < 0:
            stop += len(self)

        elif stop > len(self):
            raise ChainError(
                f"'stop={stop}' cannot be greater than account's current nonce ({len(self)})."
            )

        if stop <= start:
            return []  # nothing to query

        return cast(
            list[ReceiptAPI],
            list(
                self.query_manager.query(
                    AccountTransactionQuery(
                        columns=list(ReceiptAPI.__pydantic_fields__),
                        account=self.address,
                        start_nonce=start,
                        stop_nonce=stop - 1,
                        step=step,
                    )
                )
            ),
        )

    def append(self, receipt: ReceiptAPI):
        """
        Add a receipt to the sessional cache.

        Args:
            receipt (:class:`~ape.api.transactions.ReceiptAPI`): The receipt to append.
        """

        if receipt.txn_hash not in [x.txn_hash for x in self.sessional]:
            self.sessional.append(receipt)

    def revert_to_block(self, block_number: int):
        """
        Remove all receipts after the given block number.

        Args:
            block_number (int): The block number to revert to.
        """

        self.sessional = [x for x in self.sessional if x.block_number <= block_number]


class TransactionHistory(BaseManager):
    """
    A container mapping Transaction History to the transaction from the active session.
    """

    _account_history_cache: dict[AddressType, AccountHistory] = {}
    _hash_to_receipt_map: dict[str, ReceiptAPI] = {}

    @singledispatchmethod
    def __getitem__(self, key):
        raise NotImplementedError(f"Cannot use type of {type(key)} as Index")

    @__getitem__.register
    def __getitem_base_address(self, address: BaseAddress) -> AccountHistory:
        return self._get_account_history(address)

    @__getitem__.register
    def __getitem_str(self, account_or_hash: str) -> Union[AccountHistory, ReceiptAPI]:
        """
        Get a receipt from the history by its transaction hash.
        If the receipt is not currently cached, will use the provider
        to retrieve it.

        Args:
            account_or_hash (str): The hash of the transaction.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`: The receipt.
        """

        def _get_receipt() -> Optional[ReceiptAPI]:
            try:
                return self._get_receipt(account_or_hash)
            except Exception:
                return None

        is_account = False
        if not account_or_hash.startswith("0x"):
            # Attempt converting.
            try:
                account_or_hash = self.conversion_manager.convert(account_or_hash, AddressType)
            except Exception:
                # Pretend this never happened.
                pass
            else:
                is_account = True

        try:
            address = self.provider.network.ecosystem.decode_address(account_or_hash)
            history = self._get_account_history(address)
            if len(history) > 0:
                return history

        except Exception as err:
            msg = f"'{account_or_hash}' is not a known address or transaction hash."
            if is_account:
                raise ChainError(msg) from err

            # Try to treat as transaction hash.
            elif receipt := _get_receipt():
                return receipt

            # Not an account or tx hash (with success).
            raise ChainError(msg) from err

        # No account history found. Check for transaction hash.
        if receipt := _get_receipt():
            return receipt

        # Nothing found. Return empty history
        return history

    def _get_receipt(self, txn_hash: str) -> ReceiptAPI:
        if cached_receipt := self._hash_to_receipt_map.get(txn_hash):
            return cached_receipt

        receipt = self.provider.get_receipt(txn_hash, timeout=0)
        self.append(receipt)
        return receipt

    def append(self, txn_receipt: ReceiptAPI):
        """
        Add a transaction to the cache This is useful for sessional-transactions.

        Raises:
            :class:`~ape.exceptions.ChainError`: When trying to append a transaction
              receipt that is already in the list.

        Args:
            txn_receipt (:class:`~ape.api.transactions.ReceiptAPI`): The transaction receipt.
        """

        self._hash_to_receipt_map[txn_receipt.txn_hash] = txn_receipt
        key = txn_receipt.sender or ZERO_ADDRESS
        address = self.conversion_manager.convert(key, AddressType)
        if address not in self._account_history_cache:
            self._account_history_cache[address] = AccountHistory(address=address)

        self._account_history_cache[address].append(txn_receipt)

    def revert_to_block(self, block_number: int):
        """
        Remove all receipts past the given block number.

        Args:
            block_number (int): The block number to revert to.
        """

        self._hash_to_receipt_map = {
            h: r for h, r in self._hash_to_receipt_map.items() if r.block_number <= block_number
        }
        for account_history in self._account_history_cache.values():
            account_history.revert_to_block(block_number)

    def _get_account_history(self, address: Union[BaseAddress, AddressType]) -> AccountHistory:
        address_key: AddressType = self.conversion_manager.convert(address, AddressType)

        if address_key not in self._account_history_cache:
            self._account_history_cache[address_key] = AccountHistory(address=address_key)

        return self._account_history_cache[address_key]


class ReportManager(BaseManager):
    """
    A class representing the active Ape session. Useful for tracking data and
    building reports.

    **NOTE**: This class is not part of the public API.
    """

    def show_gas(self, report: "GasReport", file: Optional[IO[str]] = None):
        tables: list[Table] = []

        for contract_id, method_calls in report.items():
            title = f"{contract_id} Gas"
            table = Table(title=title, box=SIMPLE)
            table.add_column("Method")
            table.add_column("Times called", justify="right")
            table.add_column("Min.", justify="right")
            table.add_column("Max.", justify="right")
            table.add_column("Mean", justify="right")
            table.add_column("Median", justify="right")
            has_at_least_1_row = False

            for method_call, gases in sorted(method_calls.items()):
                if not gases:
                    continue

                if not method_call or is_zero_hex(method_call) or is_evm_precompile(method_call):
                    continue

                elif method_call == "__new__":
                    # Looks better in the gas report.
                    method_call = "__init__"

                has_at_least_1_row = True
                table.add_row(
                    method_call,
                    f"{len(gases)}",
                    f"{min(gases)}",
                    f"{max(gases)}",
                    f"{int(round(mean(gases)))}",
                    f"{int(round(median(gases)))}",
                )

            if has_at_least_1_row:
                tables.append(table)

        self.echo(*tables, file=file)

    def echo(
        self, *rich_items, file: Optional[IO[str]] = None, console: Optional["RichConsole"] = None
    ):
        console = console or get_rich_console(file)
        console.print(*rich_items)

    def show_source_traceback(
        self,
        traceback: "SourceTraceback",
        file: Optional[IO[str]] = None,
        console: Optional["RichConsole"] = None,
        failing: bool = True,
    ):
        console = console or get_rich_console(file)
        style = "red" if failing else None
        console.print(str(traceback), style=style)

    def show_events(
        self, events: list, file: Optional[IO[str]] = None, console: Optional["RichConsole"] = None
    ):
        console = console or get_rich_console(file)
        console.print("Events emitted:")
        for event in events:
            console.print(event)

    def _get_console(self, *args, **kwargs):
        # TODO: Delete this method in v0.9.
        # It only exists for backwards compat.
        return get_rich_console(*args, **kwargs)


class ChainManager(BaseManager):
    """
    A class for managing the state of the active blockchain.
    Also handy for querying data about the chain and managing local caches.
    Access the chain manager singleton from the root ``ape`` namespace.

    Usage example::

        from ape import chain
    """

    _snapshots: defaultdict = defaultdict(list)  # chain_id -> snapshots
    _chain_id_map: dict[str, int] = {}
    _block_container_map: dict[int, BlockContainer] = {}
    _transaction_history_map: dict[int, TransactionHistory] = {}
    _reports: ReportManager = ReportManager()

    @cached_property
    def contracts(self) -> ContractCache:
        """
        A manager for cached contract-types, proxy info, and more.
        """
        return ContractCache()

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
    def history(self) -> TransactionHistory:
        """
        A mapping of transactions from the active session to the account responsible.
        """
        try:
            chain_id = self.chain_id
        except ProviderNotConnectedError:
            return TransactionHistory()  # Empty list.

        if chain_id not in self._transaction_history_map:
            history = TransactionHistory()
            self._transaction_history_map[chain_id] = history

        return self._transaction_history_map[chain_id]

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
        self.provider.set_timestamp(self.conversion_manager.convert(new_value, int))

    @log_instead_of_fail(default="<ChainManager>")
    def __repr__(self) -> str:
        props = f"id={self.chain_id}" if self.network_manager.active_provider else "disconnected"
        cls_name = getattr(type(self), "__name__", ChainManager.__name__)
        return f"<{cls_name} ({props})>"

    def snapshot(self) -> "SnapshotID":
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
        chain_id = self.provider.chain_id
        snapshot_id = self.provider.snapshot()
        if snapshot_id not in self._snapshots[chain_id]:
            self._snapshots[chain_id].append(snapshot_id)

        return snapshot_id

    def restore(self, snapshot_id: Optional["SnapshotID"] = None):
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
        chain_id = self.provider.chain_id
        if snapshot_id is None and not self._snapshots[chain_id]:
            raise ChainError("There are no snapshots to revert to.")
        elif snapshot_id is None:
            snapshot_id = self._snapshots[chain_id].pop()
        elif snapshot_id not in self._snapshots[chain_id]:
            raise UnknownSnapshotError(snapshot_id)
        else:
            snapshot_index = self._snapshots[chain_id].index(snapshot_id)
            self._snapshots[chain_id] = self._snapshots[chain_id][:snapshot_index]

        self.provider.restore(snapshot_id)
        self.history.revert_to_block(self.blocks.height)

    @contextmanager
    def isolate(self):
        """
        Run code in an isolated context.
        Requires using a local provider that supports snapshotting.

        Usages example::

            owner = accounts[0]
            with chain.isolate():
                contract = owner.deploy(project.MyContract)
                receipt = contract.fooBar(sender=owner)
        """

        snapshot = None
        try:
            snapshot = self.snapshot()
        except APINotImplementedError:
            logger.warning("Provider does not support snapshotting.")
        pending = self.pending_timestamp

        start_ecosystem_name = self.provider.network.ecosystem.name
        start_network_name = self.provider.network.name
        start_provider_name = self.provider.name

        try:
            yield
        finally:
            if snapshot is None:
                logger.error("Failed to create snapshot.")
                return

            end_ecosystem_name = self.provider.network.ecosystem.name
            end_network_name = self.provider.network.name
            end_provider_name = self.provider.name

            if (
                start_ecosystem_name != end_ecosystem_name
                or start_network_name != end_network_name
                or start_provider_name != end_provider_name
            ):
                logger.warning("Provider changed before isolation completed.")
                return

            self.chain_manager.restore(snapshot)

            try:
                self.pending_timestamp = pending
            except APINotImplementedError:
                # Provider does not support time travel.
                pass

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
                Defaults to None.
        """
        if timestamp and deltatime:
            raise ValueError("Cannot give both `timestamp` and `deltatime` arguments together.")
        if timestamp:
            self.pending_timestamp = timestamp
        elif deltatime:
            self.pending_timestamp += deltatime
        self.provider.mine(num_blocks)

    def set_balance(self, account: Union[BaseAddress, AddressType], amount: Union[int, str]):
        if isinstance(account, BaseAddress):
            account = account.address

        if isinstance(amount, str) and len(str(amount).split(" ")) > 1:
            # Support values like "1000 ETH".
            amount = self.conversion_manager.convert(amount, int)
        elif isinstance(amount, str):
            # Support hex strings
            amount = int(amount, 16)

        return self.provider.set_balance(account, amount)

    def get_receipt(self, transaction_hash: str) -> ReceiptAPI:
        """
        Get a transaction receipt from the chain.

        Args:
            transaction_hash (str): The hash of the transaction.

        Returns:
            :class:`~ape.apt.transactions.ReceiptAPI`
        """
        receipt = self.chain_manager.history[transaction_hash]
        if not isinstance(receipt, ReceiptAPI):
            raise TransactionNotFoundError(transaction_hash=transaction_hash)

        return receipt
