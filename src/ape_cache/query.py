import json
import shutil
from collections.abc import Iterator
from functools import singledispatchmethod
from pathlib import Path
from typing import TYPE_CHECKING

from ape.api.providers import BlockAPI
from ape.api.query import BaseInterfaceModel, BlockQuery, CursorAPI, QueryEngineAPI, QueryType
from ape.exceptions import QueryEngineError

if TYPE_CHECKING:
    try:
        # Only on Python 3.11
        from typing import Self  # type: ignore
    except ImportError:
        from typing_extensions import Self  # type: ignore


class _BaseCursor(CursorAPI):
    cache_folder: Path

    @property
    def total_time(self) -> float:
        return (self.query.end_index - self.query.start_index) * (self.time_per_row)

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


class CacheQueryProvider(QueryEngineAPI):
    """
    Default implementation of the :class:`~ape.api.query.QueryAPI`.
    Allows for the query of blockchain data using a connected provider.
    """

    execute = singledispatchmethod(QueryEngineAPI.execute)

    def cache_folder(
        self, ecosystem_name: str | None = None, network_name: str | None = None
    ) -> Path:
        if ecosystem_name is None or network_name is None:
            ecosystem_name = self.provider.network.ecosystem.name
            network_name = self.provider.network.name

        return self.config_manager.DATA_FOLDER / ecosystem_name / network_name / "query-cache"

    def find_ranges(
        self, index_folder: Path, start: int = 0, end: int = -1
    ) -> Iterator[tuple[int, int]]:
        """Yield inclusive runs of cached indexes that exist inside ``[start, end]``."""
        if not index_folder.is_dir():
            return

        indices = sorted(int(path.name) for path in index_folder.iterdir() if path.name.isdigit())
        if end != -1:
            indices = [index for index in indices if start <= index <= end]
        else:
            indices = [index for index in indices if index >= start]

        if not indices:
            return

        run_start = previous = indices[0]
        for index in indices[1:]:
            if index == previous + 1:
                previous = index
                continue

            yield run_start, previous
            run_start = previous = index

        yield run_start, previous

    @execute.register
    def exec_block_query(self, query: BlockQuery) -> Iterator[BlockCursor]:
        index_folder = self.cache_folder() / "blocks" / ".number"
        try:
            ranges = list(
                self.find_ranges(index_folder, start=query.start_block, end=query.stop_block)
            )
        except OSError:
            return

        for start, end in ranges:
            yield BlockCursor(query=query, cache_folder=index_folder.parent).shrink(start, end)

    def cache(self, result):
        if not isinstance(result.query, BlockQuery):
            return

        folder = self.cache_folder() / "blocks" / ".number"
        folder.mkdir(parents=True, exist_ok=True)
        for block in result.as_model_iter():
            number = getattr(block, "number", None)
            if number is None:
                continue

            path = folder / str(number)
            if path.exists():
                continue

            path.write_text(block.model_dump_json())

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

    # NOTE: Delete below after v0.9
    def estimate_query(self, query: QueryType) -> int | None:
        return None

    def perform_query(self, query: QueryType) -> Iterator:
        raise QueryEngineError("Cannot use this engine in legacy mode")

    def update_cache(self, query: QueryType, result: Iterator[BaseInterfaceModel]):
        pass
