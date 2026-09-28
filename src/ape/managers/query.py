import difflib
import os
import time
from collections.abc import Iterator
from functools import cached_property, singledispatchmethod
from itertools import pairwise, tee
from typing import TYPE_CHECKING

import narwhals as nw
from pydantic import model_validator

# TODO: Switch to `import narwhals.v1 as nw` per narwhals documentation
from ape.api.query import (
    AccountTransactionQuery,
    BaseInterfaceModel,
    BlockQuery,
    BlockTransactionQuery,
    ContractEventQuery,
    CursorAPI,
    ModelType,
    QueryAPI,
    QueryEngineAPI,
    QueryType,
    resolve_dataframe_backend,
)
from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.contracts.base import ContractLog, LogFilter
from ape.exceptions import QueryEngineError
from ape.logging import logger
from ape.plugins._utils import clean_plugin_name
from ape.utils.basemodel import ManagerAccessMixin

if TYPE_CHECKING:
    from narwhals.typing import Frame

    from ape.api.providers import BlockAPI

    try:
        # Only on Python 3.11
        from typing import Self  # type: ignore
    except ImportError:
        from typing_extensions import Self  # type: ignore


def _experimental_query_enabled() -> bool:
    raw = os.environ.get("APE_ENABLE_EXPERIMENTAL_QUERY_BACKEND", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _query_step(query: QueryType) -> int:
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

    def as_dataframe(self, backend: nw.Implementation) -> "Frame":
        data: dict[str, list] = {column: [] for column in self.query.columns}

        for item in self.as_model_iter():
            for column in data:
                data[column] = getattr(item, column)

        return nw.from_dict(data, backend=backend)


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
        if (start_index and start_index != 0) or (
            end_index and end_index != self.query.num_transactions
        ):
            # NOTE: Not possible to shrink this query (also, should never need to be shrunk unless
            #       different Engines mismatch block on number of transactions in block)
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

    @singledispatchmethod
    def exec(self, query: QueryType) -> Iterator[CursorAPI]:  # type: ignore[override]
        return super().exec(query)

    @exec.register
    def exec_block_query(self, query: BlockQuery) -> Iterator[_RpcBlockCursor]:
        yield _RpcBlockCursor(query=query)

    @exec.register
    def exec_block_transaction_query(
        self, query: BlockTransactionQuery
    ) -> Iterator[_RpcBlockTransactionCursor]:
        yield _RpcBlockTransactionCursor(query=query)

    @exec.register
    def exec_contract_event_query(
        self, query: ContractEventQuery
    ) -> Iterator[_RpcContractEventCursor]:
        yield _RpcContractEventCursor(query=query)

    @exec.register
    def exec_account_transaction_query(
        self, query: AccountTransactionQuery
    ) -> Iterator[_RpcAccountTransactionCursor]:
        yield _RpcAccountTransactionCursor(query=query)

    # TODO: Remove below in v0.9
    @singledispatchmethod
    def estimate_query(self, query: QueryType) -> int | None:  # type: ignore
        return None  # can't handle this query

    @estimate_query.register
    def estimate_block_query(self, query: BlockQuery) -> int | None:
        # NOTE: Very loose estimate of 100ms per block
        return (1 + query.stop_block - query.start_block) * 100

    @estimate_query.register
    def estimate_block_transaction_query(self, query: BlockTransactionQuery) -> int:
        # NOTE: Very loose estimate of 1000ms per block for this query.
        return self.provider.get_block(query.block_id).num_transactions * 100

    @estimate_query.register
    def estimate_contract_events_query(self, query: ContractEventQuery) -> int:
        # NOTE: Very loose estimate of 100ms per block for this query.
        return (1 + query.stop_block - query.start_block) * 100

    @estimate_query.register
    def estimate_account_transactions_query(self, query: AccountTransactionQuery) -> int:
        # NOTE: Extremely expensive query, involves binary search of all blocks in a chain
        #       Very loose estimate of 5s per transaction for this query.
        return (1 + query.stop_nonce - query.start_nonce) * 5000

    @singledispatchmethod
    def perform_query(self, query: QueryType) -> Iterator:  # type: ignore
        raise QueryEngineError(f"Cannot handle '{type(query)}'.")

    @perform_query.register
    def perform_block_query(self, query: BlockQuery) -> Iterator:
        return map(
            self.provider.get_block,
            # NOTE: the range stop block is a non-inclusive stop.
            #       Where the query method is an inclusive stop.
            range(query.start_block, query.stop_block + 1, query.step),
        )

    @perform_query.register
    def perform_block_transaction_query(
        self, query: BlockTransactionQuery
    ) -> Iterator[TransactionAPI]:
        return self.provider.get_transactions_by_block(query.block_id)

    @perform_query.register
    def perform_contract_events_query(self, query: ContractEventQuery) -> Iterator[ContractLog]:
        addresses = query.contract
        if not isinstance(addresses, list):
            addresses = [query.contract]  # type: ignore

        log_filter = LogFilter.from_event(
            event=query.event,
            search_topics=query.search_topics,
            addresses=addresses,
            start_block=query.start_block,
            stop_block=query.stop_block,
        )
        return self.provider.get_contract_logs(log_filter)

    @perform_query.register
    def perform_account_transactions_query(
        self, query: AccountTransactionQuery
    ) -> Iterator[ReceiptAPI]:
        yield from self.provider.get_transactions_by_account_nonce(
            query.account, query.start_nonce, query.stop_nonce
        )


class QueryResult(CursorAPI[ModelType]):
    cursors: list[CursorAPI[ModelType]]
    """The optimal set of cursors (in sorted order) that fulfill this query."""

    @model_validator(mode="after")
    def validate_coverage(self):
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
        return nw.concat([c.as_dataframe(backend=resolved) for c in self.cursors], how="vertical")

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

    def _solve_optimal_coverage(
        self,
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

    def _experimental_query(
        self,
        query: QueryType,
        engine_to_use: str | None = None,
    ) -> QueryResult:
        if not engine_to_use:
            # One engine failing to plan must not drop every other engine.
            all_cursors = []
            for engine in self.engines.values():
                try:
                    all_cursors.extend(engine.exec(query))
                except Exception as err:  # noqa: BLE001 - a plugin must not abort planning
                    logger.debug(f"Skipping {type(engine).__name__} while planning: {err}")

            all_cursors.sort(key=lambda cursor: cursor.query)

        elif selected_engine := self.engines.get(engine_to_use):
            all_cursors = list(selected_engine.exec(query))

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

    # TODO: Replace `.query` with `._experimental_query` and remove this in v0.9
    def query(
        self,
        query: QueryType,
        engine_to_use: str | None = None,
    ) -> Iterator[BaseInterfaceModel]:
        """
        Args:
            query (``QueryType``): The type of query to execute
            engine_to_use (str | None): Short-circuit selection logic using
              a specific engine. Defaults is set by performance-based selection logic.

        Raises:
            :class:`~ape.exceptions.QueryEngineError`: When given an invalid or
          inaccessible ``engine_to_use`` value.

        Returns:
            Iterator[``BaseInterfaceModel``]
        """
        if _experimental_query_enabled():
            return self._experimental_query(query, engine_to_use=engine_to_use).as_model_iter()

        if engine_to_use:
            if engine_to_use not in self.engines:
                raise QueryEngineError(
                    f"Query engine `{engine_to_use}` not found. "
                    f"Did you mean {' or '.join(self._suggest_engines(engine_to_use))}?"
                )

            sel_engine = self.engines[engine_to_use]
            est_time = sel_engine.estimate_query(query)

        else:
            # Get heuristics from all the query engines to perform this query
            estimates = ((qe, qe.estimate_query(query)) for qe in self.engines.values())

            # Ignore query engines that can't perform this query
            valid_estimates = filter(lambda qe: qe[1] is not None, estimates)

            try:
                # Find the "best" engine to perform the query
                # NOTE: Sorted by fastest time heuristic
                sel_engine, est_time = min(valid_estimates, key=lambda qe: qe[1])  # type: ignore

            except ValueError as e:
                raise QueryEngineError("No query engines are available.") from e

        # Go fetch the result from the engine
        sel_engine_name = getattr(type(sel_engine), "__name__", None)
        query_type_name = getattr(type(query), "__name__", None)
        if not sel_engine_name:
            logger.error("Engine type unknown")
        if not query_type_name:
            logger.error("Query type unknown")

        if sel_engine_name and query_type_name:
            logger.debug(f"{sel_engine_name}: {query_type_name}({query})")

        start_time = time.time_ns()
        result = sel_engine.perform_query(query)
        exec_time = (time.time_ns() - start_time) // 1000

        if sel_engine_name and query_type_name:
            logger.debug(
                f"{sel_engine_name}: {query_type_name}"
                f" executed in {exec_time} ms (expected: {est_time} ms)"
            )

        # Update any caches
        for engine in self.engines.values():
            if not isinstance(engine, sel_engine.__class__):
                result, cache_data = tee(result)
                try:
                    engine.update_cache(query, cache_data)
                except QueryEngineError as err:
                    logger.error(str(err))

        return result
