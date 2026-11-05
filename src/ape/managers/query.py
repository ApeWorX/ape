import difflib
from collections.abc import Iterator
from functools import cached_property, singledispatchmethod
from itertools import chain, pairwise
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
    _column_values,
    _from_columns,
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


def _last_on_step(start: int, end: int, step: int) -> int:
    """The last index in ``[start, end]`` that lies on the step grid from ``start``."""
    return start + (end - start) // step * step


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
        start_nonce, stop_nonce = self.query.start_nonce, self.query.stop_nonce
        for receipt in self.provider.get_transactions_by_account_nonce(
            self.query.account, start_nonce, stop_nonce
        ):
            # A provider can return every matching transaction in the last block it
            # searched, including later nonces. Neighboring cursors own those rows.
            if start_nonce <= receipt.nonce <= stop_nonce:
                yield receipt


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
                f"Start: {cursor.query.start_index} End: {cursor.query.end_index} "
                f"Total: {cursor.total_time} seconds"
            )
            if cursor.query.end_index < cursor.query.start_index:
                raise QueryEngineError(
                    f"Cursor {i} has an empty window "
                    f"[{cursor.query.start_index}:{cursor.query.end_index}]."
                )
            assert cursor.query.start_index == current_pos, (
                f"Cursor {i} starts at {cursor.query.start_index}, expected {current_pos}"
            )
            current_pos = _last_on_step(current_pos, cursor.query.end_index, step) + step

        # A stepped query ends at its last sampled index, which can be before ``end_index``.
        last_index = _last_on_step(self.query.start_index, self.query.end_index, step)
        assert current_pos == last_index + step, (
            f"Coverage ended at {current_pos - step}, expected {last_index}"
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
        frames: list[Frame] = []

        # Cursors that build their frame from models are read into one frame, so
        # column types are inferred from every row. Separate frames infer ``Null``
        # for a window with no rows (or only empty lists), and cannot be stacked
        # onto the typed frames from other windows.
        batch: list[CursorAPI] = []

        def flush_batch():
            if batch:
                items = chain.from_iterable(cursor.as_model_iter() for cursor in batch)
                frames.append(_from_columns(_column_values(self.query.columns, items), resolved))
                batch.clear()

        for cursor in self.cursors:
            if type(cursor).as_dataframe is CursorAPI.as_dataframe:
                batch.append(cursor)
            else:
                flush_batch()
                frames.append(cursor.as_dataframe(backend=resolved))

        flush_batch()
        if not frames:
            return _from_columns({column: [] for column in self.query.columns}, resolved)

        # A plugin's own frame for an empty window has no types to reconcile. Drop it.
        frames = [
            frame for frame in frames if not isinstance(frame, nw.DataFrame) or len(frame) > 0
        ] or frames[:1]
        if len(frames) == 1:
            return frames[0]

        # A cursor frame is eager or lazy. ``concat`` cannot take that union as its type variable.
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
        # from one boundary up to, but not including, the next. A stepped query
        # ends at its last sampled index, which can be before ``end_index``.
        stop = _last_on_step(query.start_index, query.end_index, step) + step
        boundaries = {query.start_index, stop}
        for cursor in all_cursors:
            cursor_start, cursor_end = cursor.query.start_index, cursor.query.end_index
            for index in (cursor_start, _last_on_step(cursor_start, cursor_end, step) + step):
                if query.start_index <= index <= stop and _on_step(index, query.start_index, step):
                    boundaries.add(index)

        ordered_bounds = sorted(boundaries)
        position = {index: i for i, index in enumerate(ordered_bounds)}
        segments = [
            (seg_start, seg_next - step) for seg_start, seg_next in pairwise(ordered_bounds)
        ]

        def rows(first: int, last: int) -> int:
            return (last - first) // step + 1

        # Sweep the segments in order. Only cursors that started at or before a
        # segment and have not ended yet can cover it, so each segment checks the
        # cursors still active instead of every cursor.
        pending = sorted(all_cursors, key=lambda cursor: cursor.query.start_index)
        next_pending = 0
        active: list[CursorAPI] = []
        segment_best: list[CursorAPI | None] = []
        for seg_start, seg_end in segments:
            while (
                next_pending < len(pending) and pending[next_pending].query.start_index <= seg_start
            ):
                active.append(pending[next_pending])
                next_pending += 1

            active = [cursor for cursor in active if cursor.query.end_index >= seg_start]
            candidates = [cursor for cursor in active if _cursor_covers(cursor, seg_start, seg_end)]
            segment_best.append(
                min(candidates, key=lambda cursor: (cursor.time_per_row, cursor.total_time))
                if candidates
                else None
            )

        # A cursor that cannot be cut (``shrink`` raises) can still serve its whole
        # window, which may span one or more segments. Offer that window as one step.
        # Even a single segment needs this: on a stepped query the segment ends at
        # the last sampled index, which can be before the cursor's own end.
        whole_windows: dict[int, list[tuple[int, CursorAPI]]] = {}
        for cursor in all_cursors:
            cursor_start, cursor_end = cursor.query.start_index, cursor.query.end_index
            first = position.get(cursor_start)
            after = position.get(_last_on_step(cursor_start, cursor_end, step) + step)
            if first is not None and after is not None and after > first:
                whole_windows.setdefault(first, []).append((after, cursor))

        # Cheapest plan from the start to each boundary, in boundary order.
        # ``plan[i]`` is ``(cost, previous boundary, cursor, whole window)``.
        plan: list[tuple[float, int, CursorAPI, bool] | None] = [None] * len(ordered_bounds)
        cost: list[float] = [float("inf")] * len(ordered_bounds)
        cost[0] = 0.0
        for i, (seg_start, seg_end) in enumerate(segments):
            if cost[i] == float("inf"):
                continue

            if (best := segment_best[i]) is not None:
                total = cost[i] + rows(seg_start, seg_end) * best.time_per_row
                if total < cost[i + 1]:
                    cost[i + 1] = total
                    plan[i + 1] = (total, i, best, False)

            for after, cursor in whole_windows.get(i, []):
                last = ordered_bounds[after] - step
                total = cost[i] + rows(seg_start, last) * cursor.time_per_row
                # Prefer the segment plan on a tie. It is never worse when the cursor can be cut.
                if total < cost[after] - 1e-12:
                    cost[after] = total
                    plan[after] = (total, i, cursor, True)

        if cost[-1] == float("inf"):
            reached = max(i for i, value in enumerate(cost) if value != float("inf"))
            seg_start, seg_end = segments[reached]
            raise QueryEngineError(
                f"Could not solve, missing coverage in window [{seg_start}:{seg_end}]."
            )

        steps: list[tuple[CursorAPI, int, int, bool]] = []
        i = len(ordered_bounds) - 1
        while i > 0:
            entry = plan[i]
            assert entry is not None  # NOTE: Reachable boundaries always have a plan
            _, previous, cursor, whole = entry
            steps.append((cursor, ordered_bounds[previous], ordered_bounds[i] - step, whole))
            i = previous

        pieces: list[tuple[CursorAPI, int, int, bool]] = []
        for cursor, seg_start, seg_end, whole in reversed(steps):
            if (
                pieces
                and not whole
                and not pieces[-1][3]
                and pieces[-1][0] is cursor
                and pieces[-1][2] + step == seg_start
            ):
                previous_cursor, previous_start, _, _ = pieces[-1]
                pieces[-1] = (previous_cursor, previous_start, seg_end, False)
            else:
                pieces.append((cursor, seg_start, seg_end, whole))

        for cursor, seg_start, seg_end, whole in pieces:
            if whole:
                # Hand back the cursor's own window so a cursor that cannot be cut accepts it.
                yield cursor.shrink(
                    start_index=cursor.query.start_index, end_index=cursor.query.end_index
                )
            else:
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
