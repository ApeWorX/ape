import json
import os
import shutil
import tempfile
from collections.abc import Iterator
from functools import singledispatchmethod
from pathlib import Path
from typing import TYPE_CHECKING, ClassVar

from eth_utils import to_hex

from ape.api.providers import BlockAPI
from ape.api.query import BlockQuery, CursorAPI, QueryEngineAPI

if TYPE_CHECKING:
    from ape.api.providers import ProviderAPI
    from ape.managers.query import QueryResult

    try:
        # Only on Python 3.11
        from typing import Self  # type: ignore
    except ImportError:
        from typing_extensions import Self  # type: ignore


class _BaseCursor(CursorAPI):
    cache_folder: Path

    # ``total_time`` comes from ``CursorAPI``: ``len(query) * time_per_row``,
    # which counts the inclusive span and honors ``step=``.

    @property
    def time_per_row(self) -> float:
        return 0.01  # 10ms per row to parse file w/ Pydantic


class BlockCursor(_BaseCursor):
    query: BlockQuery

    def shrink(self, start_index: int | None = None, end_index: int | None = None) -> "Self":
        copy = self.model_copy(deep=True)

        if start_index is not None:
            copy.query.start_block = start_index

        if end_index is not None:
            copy.query.stop_block = end_index

        return copy

    def as_model_iter(self) -> Iterator[BlockAPI]:
        block_index_folder = self.cache_folder / ".number"
        decode_block = self.provider.network.ecosystem.decode_block
        step = self.query.step or 1
        for block_number in range(self.query.start_block, self.query.stop_block + 1, step):
            path = block_index_folder / str(block_number)
            if not path.is_file():
                continue

            yield decode_block(json.loads(path.read_text()))


def _write_block(index_folder: Path, block: BlockAPI):
    number = getattr(block, "number", None)
    if number is None:
        return

    path = index_folder / str(number)
    if path.exists():
        return

    # ``transactions`` loads the block body from the node. The file stores
    # the header fields that are already on the model.
    # Write to a sibling tempfile first, then rename into place so an
    # interrupted write never leaves truncated JSON for a later read.
    fd, tmp_name = tempfile.mkstemp(dir=index_folder, prefix=f".{number}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(block.model_dump_json(exclude={"transactions"}))
        os.replace(tmp_name, path)
    except BaseException:
        try:
            os.unlink(tmp_name)
        except OSError:
            pass
        raise


def _canonical_height(provider: "ProviderAPI") -> int:
    """
    The highest block that is part of settled history. That is the finalized
    block when the node reports one, or else the head less the network's
    required confirmations. Blocks above it can still be reorganized away.

    Returns ``-1`` (nothing is settled) when neither is known, so a failed
    finality lookup never lets an unsettled block into the cache.
    """
    try:
        finalized = provider.get_block("finalized").number  # type: ignore[arg-type]
    except Exception:  # noqa: BLE001 - not every node supports the ``finalized`` tag
        finalized = None

    if finalized is not None:
        return finalized

    confirmations = provider.network.required_confirmations
    if confirmations <= 0:
        # The head of a chain with no required confirmations can still be replaced.
        return -1

    try:
        head = provider.get_block("latest").number
    except Exception:  # noqa: BLE001 - an unknown head settles nothing
        return -1

    return -1 if head is None else head - confirmations


class _CachingBlockCursor(CursorAPI):
    """
    Wrap a block cursor from another engine, and store each block as the caller
    reads it. Nothing is fetched or written until the result is consumed.
    """

    query: BlockQuery
    inner: CursorAPI
    index_folder: Path

    def shrink(self, start_index: int | None = None, end_index: int | None = None) -> "Self":
        inner = self.inner.shrink(start_index=start_index, end_index=end_index)
        return self.model_copy(update={"inner": inner, "query": inner.query})

    @property
    def total_time(self) -> float:
        return self.inner.total_time

    @property
    def time_per_row(self) -> float:
        return self.inner.time_per_row

    def as_model_iter(self) -> Iterator[BlockAPI]:
        self.index_folder.mkdir(parents=True, exist_ok=True)
        # Files are keyed by height, so only store blocks that cannot be replaced.
        canonical_height = _canonical_height(self.provider)
        for block in self.inner.as_model_iter():
            if block.number is not None and block.number <= canonical_height:
                _write_block(self.index_folder, block)

            yield block


class CacheQueryProvider(QueryEngineAPI):
    """
    Default implementation of the :class:`~ape.api.query.QueryEngineAPI`.
    Allows for the query of blockchain data using a connected provider.
    """

    execute = singledispatchmethod(QueryEngineAPI.execute)

    # Genesis hash per (connection, chain ID), so planning does not fetch block 0 every query.
    _genesis_hashes: ClassVar[dict[tuple[str, int], str]] = {}

    def cache_folder(
        self, ecosystem_name: str | None = None, network_name: str | None = None
    ) -> Path:
        """
        The cache folder for one network. Data for each chain on that network is
        kept in its own folder below it (see :meth:`chain_cache_folder`).
        """
        if ecosystem_name is None or network_name is None:
            ecosystem_name = self.provider.network.ecosystem.name
            network_name = self.provider.network.name

        return self.config_manager.DATA_FOLDER / ecosystem_name / network_name / "query-cache"

    def chain_cache_folder(self) -> Path | None:
        """
        The cache folder for the connected chain, keyed by its chain ID and genesis
        hash. Several chains can share one network name (for example custom networks
        on different URIs), and a block height only identifies a block within one chain.

        Returns ``None`` when the chain cannot be identified. Nothing is cached then.
        """
        try:
            chain_id = self.provider.chain_id
            key = (self.provider.connection_str, chain_id)
            if (genesis_hash := self._genesis_hashes.get(key)) is None:
                if not (genesis := self.provider.get_block(0).hash):
                    return None

                genesis_hash = to_hex(genesis).lower().removeprefix("0x")
                self._genesis_hashes[key] = genesis_hash

        except Exception:  # noqa: BLE001 - an unidentified chain is not cached
            return None

        return self.cache_folder() / str(chain_id) / genesis_hash

    @staticmethod
    def find_ranges(
        index_folder: Path, start: int = 0, end: int = -1, step: int = 1
    ) -> Iterator[tuple[int, int]]:
        """
        Yield inclusive runs of cached indexes that exist inside ``[start, end]``.
        Only indexes on the ``step`` grid from ``start`` count, and a run joins
        indexes that are ``step`` apart.
        """
        if not index_folder.is_dir():
            return

        indices = sorted(int(path.name) for path in index_folder.iterdir() if path.name.isdigit())
        indices = [
            index
            for index in indices
            if index >= start and (end == -1 or index <= end) and (index - start) % step == 0
        ]
        if not indices:
            return

        run_start = previous = indices[0]
        for index in indices[1:]:
            if index == previous + step:
                previous = index
                continue

            yield run_start, previous
            run_start = previous = index

        yield run_start, previous

    @property
    def uses_cache(self) -> bool:
        """
        Local chains (including forks) are reset, reverted and re-mined between
        sessions, so a height does not identify one block there. Those are not cached.
        """
        return not self.provider.network.is_dev

    @execute.register
    def exec_block_query(self, query: BlockQuery) -> Iterator[BlockCursor]:
        if not self.uses_cache:
            return

        if (chain_folder := self.chain_cache_folder()) is None:
            return

        index_folder = chain_folder / "blocks" / ".number"
        try:
            ranges = list(
                self.find_ranges(
                    index_folder, start=query.start_block, end=query.stop_block, step=query.step
                )
            )
        except OSError:
            return

        for start, end in ranges:
            yield BlockCursor(query=query, cache_folder=index_folder.parent).shrink(start, end)

    def cache(self, result: "QueryResult"):
        if not isinstance(result.query, BlockQuery) or not self.uses_cache:
            return

        if (chain_folder := self.chain_cache_folder()) is None:
            return

        # Store blocks as the caller reads them, so the cache never fetches a block
        # the caller did not ask for, and never fetches one twice.
        index_folder = chain_folder / "blocks" / ".number"
        for i, cursor in enumerate(result.cursors):
            if isinstance(cursor, (BlockCursor, _CachingBlockCursor)):
                # Already on disk, or already wrapped.
                continue

            if type(cursor).as_dataframe is not CursorAPI.as_dataframe:
                # The engine builds its own frame without block models. Keep that path.
                continue

            result.cursors[i] = _CachingBlockCursor(
                query=cursor.query, inner=cursor, index_folder=index_folder
            )

    def prune_database(self, ecosystem_name: str, network_name: str):
        """
        Remove the file cache for one network.

        Args:
            ecosystem_name (str): Name of the ecosystem (ex: ethereum).
            network_name (str): Name of the network (ex: mainnet).
        """
        path = self.cache_folder(ecosystem_name, network_name)
        if path.is_dir():
            shutil.rmtree(path)
