from collections.abc import Iterator
from functools import singledispatchmethod
from pathlib import Path
from typing import TYPE_CHECKING, Optional

import narwhals as nw

from ape.api.providers import BlockAPI
from ape.api.query import BaseInterfaceModel, BlockQuery, CursorAPI, QueryEngineAPI, QueryType
from ape.exceptions import QueryEngineError

if TYPE_CHECKING:
    from narwhals.typing import Frame

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

    def shrink(self, start_index: Optional[int] = None, end_index: Optional[int] = None) -> "Self":
        copy = self.model_copy(deep=True)

        if start_index is not None:
            copy.query.start_block = start_index

        if end_index is not None:
            copy.query.stop_block = end_index

        return copy

    def as_dataframe(self, backend: nw.Implementation) -> "Frame":
        return super().as_dataframe(backend)

    def as_model_iter(self) -> Iterator[BlockAPI]:
        block_index_folder = self.cache_folder / ".number"
        for block_number in range(self.query.start_block, self.query.stop_block + 1):
            yield from map(
                self.provider.network.ecosystem.block_class.model_validate_json,
                (block_index_folder / str(block_number)).read_text(),
            )


class CacheQueryProvider(QueryEngineAPI):
    """
    Default implementation of the :class:`~ape.api.query.QueryAPI`.
    Allows for the query of blockchain data using a connected provider.
    """

    exec = singledispatchmethod(QueryEngineAPI.exec)

    def cache_folder(self) -> Path:
        return (
            self.config_manager.DATA_FOLDER
            / self.provider.network.ecosystem.name
            / self.provider.network.name
        )

    def find_ranges(
        self, index_folder: Path, start: int = 0, end: int = -1
    ) -> Iterator[tuple[int, int]]:
        all_indices = sorted(int(p.name) for p in index_folder.glob("*"))
        last_index = max(start, min(all_indices))

        for index in all_indices:
            if index <= last_index:
                continue  # NOTE: Skip past `last_index`

            elif end != -1 and index >= end:
                # NOTE: Yield last range in `[start, end]`
                yield start, end
                break

            elif index - last_index > 1:
                # NOTE: Gap identified
                yield start, last_index
                start = index

            last_index = index

    @exec.register
    def exec_block_query(self, query: BlockQuery) -> Iterator[BlockCursor]:
        if not (block_folder := self.cache_folder() / "blocks").exists():
            return

        for block_range in self.find_ranges(
            block_folder / ".number",
            start=query.start_block,
            end=query.stop_block,
        ):
            yield BlockCursor(query=query, cache_folder=block_folder).shrink(*block_range)

    def prune_database(self, ecosystem_name: str, network_name: str):
        """
        Removes the SQLite database file from disk.

        Args:
            ecosystem_name (str): Name of the ecosystem to store data for (ex: ethereum)
            network_name (str): name of the network to store data for (ex: mainnet)

        Raises:
            :class:`~ape.exceptions.QueryEngineError`: When the database has not been initialized
        """

    # NOTE: Delete below after v0.9
    def estimate_query(self, query: QueryType) -> Optional[int]:
        return None

    def perform_query(self, query: QueryType) -> Iterator:
        raise QueryEngineError("Cannot use this engine in legacy mode")

    def update_cache(self, query: QueryType, result: Iterator[BaseInterfaceModel]):
        pass  # TODO: Add legacy cache support
