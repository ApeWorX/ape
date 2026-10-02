import difflib
from collections.abc import Iterator
from functools import cached_property, singledispatchmethod
from itertools import pairwise
from typing import TYPE_CHECKING, Any, cast

import narwhals.stable.v2 as nw
from pydantic import model_validator

from ape.api.query import (
    AccountTransactionQuery,
    BlockQuery,
    BlockTransactionQuery,
    ContractEventQuery,
    CursorAPI,
    ModelType,
    QueryAPI,
    QueryEngineAPI,
    QueryType,
    _BaseQuery,
    resolve_dataframe_backend,
)
from ape.api.transactions import TransactionAPI
from ape.contracts.base import ContractLog, LogFilter
from ape.exceptions import QueryEngineError
from ape.logging import logger
from ape.plugins._utils import clean_plugin_name
from ape.utils.basemodel import ManagerAccessMixin

if TYPE_CHECKING:
    from narwhals.stable.v2.typing import Frame

    from ape.api.providers import BlockAPI

    try:
        # Only on Python 3.11
        from typing import Self  # type: ignore
    except ImportError:
        from typing_extensions import Self  # type: ignore


def _query_step(query: _BaseQuery[Any]) -> int:
    return getattr(query, "step", 1) or 1


def _on_step(index: int, start: int, step: int) -> bool:
    return (index - start) % step == 0


def _cursor_covers(cursor: CursorAPI, start: int, end: int) -> bool:
    if cursor.query.start_index > start or cursor.query.end_index < end:
        return False

    try:
        cursor.shrink(start_index=start, end_index=end)
    except NotImplementedError:
        return False

    return True


class _RpcCursor(CursorAPI):
    def shrink(
        self,
        start_index: int | None = None,
        end_index: int | None = None,
    ) -> "Self":
        copy = self.model_copy(deep=True)

        if start_index is not None:
            copy.query.start_block = start_index

        if end_index is not None:
            copy.query.stop_block = end_index

        return copy

    @property
    def time_per_row(self) -> float:
        # NOTE: Very loose estimate of 100ms per item
        return 0.1  # seconds


class _RpcBlockCursor(_RpcCursor):
    query: BlockQuery

    def as_model_iter(self) -> Iterator["BlockAPI"]:
        return map(
            self.provider.get_block,
            # NOTE: the range stop block is a non-inclusive stop.
            #       Where the query method is an inclusive stop.
            range(self.query.start_block, self.query.stop_block + 1, self.query.step),
        )


class _RpcBlockTransactionCursor(_RpcCursor):
    query: BlockTransactionQuery

    # TODO: Move to default implementation in `CursorAPI`? (remove `@abstractmethod`)
    def shrink(
        self,
        start_index: int | None = None,
        end_index: int | None = None,
    ) -> "Self":
        start = self.query.start_index if start_index is None else start_index
        end = self.query.end_index if end_index is None else end_index
        if start != self.query.start_index or end != self.query.end_index:
            # A block's transactions are one window. Partial cuts are not representable.
            raise NotImplementedError

        return self

    def as_model_iter(self) -> Iterator[TransactionAPI]:
        if self.query.num_transactions > 0:
            yield from self.provider.get_transactions_by_block(self.query.block_id)


class _RpcContractEventCursor(_RpcCursor):
    query: ContractEventQuery

    def as_model_iter(self) -> Iterator[ContractLog]:
        addresses = self.query.contract
        if not isinstance(addresses, list):
            addresses = [self.query.contract]  # type: ignore

        log_filter = LogFilter.from_event(
            event=self.query.event,
            search_topics=self.query.search_topics,
            addresses=addresses,
            start_block=self.query.start_block,
            stop_block=self.query.stop_block,
        )
        return self.provider.get_contract_logs(log_filter)


class _RpcAccountTransactionCursor(_RpcCursor):
    query: AccountTransactionQuery

    def shrink(
        self,
        start_index: int | None = None,
        end_index: int | None = None,
    ) -> "Self":
        copy = self.model_copy(deep=True)

        if start_index is not None:
            copy.query.start_nonce = start_index

        if end_index is not None:
            copy.query.stop_nonce = end_index

        return copy

    @property
    def time_per_row(self) -> float:
        # NOTE: Extremely expensive query, involves binary search of all blocks in a chain
        #       Very loose estimate of 5s per transaction for this query.
        return 5.0

    def as_model_iter(self) -> Iterator[TransactionAPI]:
        yield from self.provider.get_transactions_by_account_nonce(
            self.query.account, self.query.start_nonce, self.query.stop_nonce
        )


class DefaultQueryProvider(QueryEngineAPI):
    """
    Default implementation of the :class:`~ape.api.query.QueryEngineAPI`.
    Allows for the query of blockchain data using connected provider.
    """

    execute = singledispatchmethod(QueryEngineAPI.execute)

    @execute.register
    def exec_block_query(self, query: BlockQuery) -> Iterator[_RpcBlockCursor]:
        yield _RpcBlockCursor(query=query)

    @execute.register
    def exec_block_transaction_query(
        self, query: BlockTransactionQuery
    ) -> Iterator[_RpcBlockTransactionCursor]:
        yield _RpcBlockTransactionCursor(query=query)

    @execute.register
    def exec_contract_event_query(
        self, query: ContractEventQuery
    ) -> Iterator[_RpcContractEventCursor]:
        yield _RpcContractEventCursor(query=query)

    @execute.register
    def exec_account_transaction_query(
        self, query: AccountTransactionQuery
    ) -> Iterator[_RpcAccountTransactionCursor]:
        yield _RpcAccountTransactionCursor(query=query)


class QueryResult(CursorAPI[ModelType]):
    cursors: list[CursorAPI[ModelType]]
    """The optimal set of cursors (in sorted order) that fulfill this query."""

    @model_validator(mode="after")
    def validate_coverage(self) -> "Self":
        # NOTE: This is done to assert that we have full coverage of queries during testing
        #       (both testing Core and in 2nd/3rd party plugins)
        step = _query_step(self.query)
        current_pos = self.query.start_index
        if self.query.end_index < current_pos:
            if self.cursors:
                raise QueryEngineError(f"{type(self.query).__name__} is empty but has cursors.")
            return self

        for i, cursor in enumerate(self.cursors):
            logger.debug(
                "Start:",
                cursor.query.start_index,
                "End:",
                cursor.query.end_index,
                "Total:",
                cursor.total_time,
                "seconds",
            )
            if cursor.query.end_index < cursor.query.start_index:
                raise QueryEngineError(
                    f"Cursor {i} has an empty window "
                    f"[{cursor.query.start_index}:{cursor.query.end_index}]."
                )
            assert cursor.query.start_index == current_pos, (
                f"Cursor {i} starts at {cursor.query.start_index}, expected {current_pos}"
            )
            current_pos = cursor.query.end_index + step

        assert current_pos == self.query.end_index + step, (
            f"Coverage ended at {current_pos - step}, expected {self.query.end_index}"
        )

        return self

    @property
    def total_time(self) -> float:
        return sum(c.total_time for c in self.cursors)

    @property
    def time_per_row(self) -> float:
        rows = sum(len(c.query) for c in self.cursors)
        if not rows:
            return 0.0

        return self.total_time / rows

    # Conversion out to fulfill user query requirements
    def as_dataframe(
        self,
        backend: str | nw.Implementation | None = None,
    ) -> "Frame":
        resolved = resolve_dataframe_backend(backend, self.config_manager.query.backend)
        # A cursor frame is eager or lazy. ``concat`` cannot take that union as its type variable.
        frames = [cursor.as_dataframe(backend=resolved) for cursor in self.cursors]
        return nw.concat(cast("list[nw.DataFrame[Any]]", frames), how="vertical")

    def as_model_iter(self) -> Iterator[ModelType]:
        for result in self.cursors:
            yield from result.as_model_iter()


class QueryManager(ManagerAccessMixin):
    """
    A singleton that manages query engines and performs queries.

    Args:
        query (``QueryType``): query to execute

    Usage example::

         biggest_block_size = chain.blocks.query("size").max()
    """

    @cached_property
    def engines(self) -> dict[str, QueryAPI]:
        """
        A dict of all :class:`~ape.api.query.QueryAPI` instances across all
        installed plugins.

        Returns:
            dict[str, :class:`~ape.api.query.QueryAPI`]
        """

        engines: dict[str, QueryAPI] = {"__default__": DefaultQueryProvider()}

        for plugin_name, engine_class in self.plugin_manager.query_engines:
            engine_name = clean_plugin_name(plugin_name)
            engines[engine_name] = engine_class()  # type: ignore

        return engines

    def _suggest_engines(self, engine_selection):
        return difflib.get_close_matches(engine_selection, list(self.engines), cutoff=0.6)

    @staticmethod
    def _solve_optimal_coverage(
        query: QueryType,
        all_cursors: list[CursorAPI],
    ) -> Iterator[CursorAPI]:
        step = _query_step(query)
        if query.end_index < query.start_index:
            return

        # Boundaries are on the query's step grid. A segment is the inclusive span
        # from one boundary up to, but not including, the next.
        boundaries = {query.start_index, query.end_index + step}
        for cursor in all_cursors:
            for index in (cursor.query.start_index, cursor.query.end_index + step):
                if query.start_index <= index <= query.end_index + step and _on_step(
                    index, query.start_index, step
                ):
                    boundaries.add(index)

        pieces: list[tuple[CursorAPI, int, int]] = []
        for seg_start, seg_next in pairwise(sorted(boundaries)):
            seg_end = seg_next - step
            if seg_end < seg_start:
                continue

            candidates = [
                cursor for cursor in all_cursors if _cursor_covers(cursor, seg_start, seg_end)
            ]
            if not candidates:
                raise QueryEngineError(
                    f"Could not solve, missing coverage in window [{seg_start}:{seg_end}]."
                )

            best = min(candidates, key=lambda cursor: (cursor.time_per_row, cursor.total_time))
            if pieces and pieces[-1][0] is best and pieces[-1][2] + step == seg_start:
                previous, previous_start, _ = pieces[-1]
                pieces[-1] = (previous, previous_start, seg_end)
            else:
                pieces.append((best, seg_start, seg_end))

        for cursor, seg_start, seg_end in pieces:
            yield cursor.shrink(start_index=seg_start, end_index=seg_end)

    def query(
        self,
        query: QueryType,
        engine_to_use: str | None = None,
    ) -> QueryResult:
        """
        Plan ``query`` and return the solved cursor.

        Call :meth:`~ape.managers.query.QueryResult.as_dataframe` for a user-facing
        ``.query`` result, or :meth:`~ape.managers.query.QueryResult.as_model_iter`
        when the caller needs the model objects.

        Args:
            query (``QueryType``): The type of query to execute.
            engine_to_use (str | None): Limit planning to one engine.
              Every engine contributes cursors when this is not set.

        Raises:
            :class:`~ape.exceptions.QueryEngineError`: When given an invalid or
              inaccessible ``engine_to_use`` value, or when the query has no coverage.

        Returns:
            :class:`~ape.managers.query.QueryResult`
        """
        if not engine_to_use:
            # One engine failing to plan must not drop every other engine.
            all_cursors: list[CursorAPI] = []
            for engine in self.engines.values():
                try:
                    all_cursors.extend(engine.execute(query))
                except Exception as err:  # noqa: BLE001 - a plugin must not abort planning
                    logger.debug(f"Skipping {type(engine).__name__} while planning: {err}")

            all_cursors.sort(key=lambda cursor: cursor.query)

        elif selected_engine := self.engines.get(engine_to_use):
            all_cursors = list(selected_engine.execute(query))

        else:
            raise QueryEngineError(
                f"Query engine `{engine_to_use}` not found. "
                f"Did you mean {' or '.join(self._suggest_engines(engine_to_use))}?"
            )

        if len(all_cursors) == 0:
            # NOTE: Likely indicates a problem with the default or selected query engine
            raise QueryEngineError(f"No data available for {query.__class__.__name__}")

        logger.debug("Sorted cursors:\n  " + "\n  ".join(map(str, all_cursors)))
        result: QueryResult = QueryResult(
            query=query,
            cursors=list(self._solve_optimal_coverage(query, all_cursors)),
        )

        # TODO: Execute in background thread when async support introduced
        for engine_name, engine in self.engines.items():
            logger.debug(f"Caching w/ '{engine_name}' ...")
            engine.cache(result)
            logger.debug(f"Caching done for '{engine_name}'")

        return result
