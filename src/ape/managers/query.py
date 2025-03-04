import difflib
import os
import time
from collections.abc import Iterator
from functools import cached_property, singledispatchmethod
from itertools import tee
from typing import TYPE_CHECKING, Optional, Union, cast

import narwhals as nw
from pydantic import model_validator

# TODO: Switch to `import narwhals.v1 as nw` per narwhals documentation
from ape.api.query import (
    AccountTransactionQuery,
    BaseCursorAPI,
    BaseInterfaceModel,
    BlockQuery,
    BlockTransactionQuery,
    ContractEventQuery,
    ModelType,
    QueryAPI,
    QueryEngineAPI,
    QueryType,
)
from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.contracts.base import ContractLog, LogFilter
from ape.exceptions import QueryEngineError
from ape.logging import logger
from ape.plugins._utils import clean_plugin_name
from ape.utils.basemodel import ManagerAccessMixin

try:
    from itertools import pairwise

except ImportError:
    # TODO: Remove when 3.9 dropped (`itertools.pairwise` introduced in 3.10)
    from more_itertools import pairwise  # type: ignore[no-redef,assignment]


if TYPE_CHECKING:
    from narwhals.typing import Frame

    from ape.api.providers import BlockAPI

    try:
        # Only on Python 3.11
        from typing import Self  # type: ignore
    except ImportError:
        from typing_extensions import Self  # type: ignore


class _RpcCursor(BaseCursorAPI):
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
    def total_time(self) -> float:
        return self.time_per_row * (1 + self.query.end_index - self.query.start_index)

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

    # TODO: Move to default implementation in `BaseCursorAPI`? (remove `@abstractmethod`)
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

    def __init__(self):
        # TODO: What is this for?
        self.supports_contract_creation = None

    @QueryEngineAPI.exec.register
    def exec_block_query(self, query: BlockQuery) -> Iterator[_RpcBlockCursor]:
        yield _RpcBlockCursor(query=query)

    @QueryEngineAPI.exec.register
    def exec_block_transaction_query(
        self, query: BlockTransactionQuery
    ) -> Iterator[_RpcBlockTransactionCursor]:
        yield _RpcBlockTransactionCursor(query=query)

    @QueryEngineAPI.exec.register
    def exec_contract_event_query(
        self, query: ContractEventQuery
    ) -> Iterator[_RpcContractEventCursor]:
        yield _RpcContractEventCursor(query=query)

    @QueryEngineAPI.exec.register
    def exec_account_transaction_query(
        self, query: AccountTransactionQuery
    ) -> Iterator[_RpcAccountTransactionCursor]:
        yield _RpcAccountTransactionCursor(query=query)

    # TODO: Remove below in v0.9
    @singledispatchmethod
    def estimate_query(self, query: QueryType) -> Optional[int]:  # type: ignore
        return None  # can't handle this query

    @estimate_query.register
    def estimate_block_query(self, query: BlockQuery) -> Optional[int]:
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


class QueryResult(BaseCursorAPI):
    cursors: list[BaseCursorAPI]
    """The optimal set of cursors (in sorted order) that fulfill this query."""

    @model_validator(mode="after")
    def validate_coverage(self):
        # NOTE: This is done to assert that we have full coverage of queries during testing
        #       (both testing Core and in 2nd/3rd party plugins)
        current_pos = self.query.start_index
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
            assert (
                cursor.query.start_index == current_pos
            ), f"Cursor {i} starts at {cursor.query.start_index}, expected {current_pos}"
            current_pos = cursor.query.end_index + 1

        assert (
            current_pos == self.query.end_index + 1
        ), f"Coverage ended at {current_pos - 1}, expected {self.query.end_index}"

        return self

    # TODO: Move to `BaseCursorAPI` and don't have `@abstractmethod`?
    def shrink(self, start_index: int | None = None, end_index: int | None = None) -> "Self":
        raise NotImplementedError

    @property
    def total_time(self) -> float:
        return sum(c.total_time for c in self.cursors)

    @property
    def time_per_row(self) -> float:
        return self.total_time / sum(len(c.query) for c in self.cursors)

    # Conversion out to fulfill user query requirements
    def as_dataframe(
        self,
        backend: Union[str, nw.Implementation, None] = None,
    ) -> "Frame":
        if backend is None:
            backend = cast(nw.Implementation, self.config_manager.config.query.backend)

        elif isinstance(backend, str):
            backend = nw.Implementation.from_backend(backend)

        assert isinstance(backend, str)

        # TODO: Source `backend` from core `query:` config if defaulted to `None`
        return nw.concat([c.as_dataframe(backend=backend) for c in self.cursors], how="vertical")

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
        all_cursors: list[BaseCursorAPI],
    ) -> Iterator[BaseCursorAPI]:
        # NOTE: Use this to reduce the amount of brute force iteration over query window
        query_segments = sorted(
            set(
                [c.query.start_index for c in all_cursors]
                + [c.query.end_index for c in all_cursors]
            )
        )

        # Find the best cursor that fits each path segment in `cursor_to_use`
        # NOTE: Prime these variables for every time "best cursor" gets yielded
        last_start_index = query.start_index
        # NOTE: Start with smallest cursor by coverage and total time
        #       (resolves corner case when `query.start_index` == `query.end_index`)
        last_best_cursor = min(all_cursors, key=lambda c: (c.query, c.total_time))
        for start_index, end_index in pairwise(query_segments):

            lowest_unit_time = float("inf")
            best_cursor = None
            for cursor in all_cursors:
                # NOTE: Cursor window must at least contain path segment
                if cursor.query.start_index <= start_index and cursor.query.end_index >= end_index:
                    # NOTE: Allow cursor to use previous segment(s) if it was the last best
                    #       since time should typically be better with larger coverage
                    shrunk_cursor = cursor.shrink(
                        start_index=(
                            last_start_index
                            if last_best_cursor and last_best_cursor is cursor
                            else start_index
                        )
                    )
                    if shrunk_cursor.time_per_row < lowest_unit_time:
                        lowest_unit_time = shrunk_cursor.time_per_row
                        # NOTE: Save original cursor to shrink later (not shrunk one)
                        best_cursor = cursor

            if best_cursor is None:
                # NOTE: `AssertionError` because this should not be possible due to RPC engine
                raise AssertionError(
                    f"Could not solve, missing coverage in window [{start_index}:{end_index}]."
                )
            logger.debug(f"Best cursor for segment [{start_index}:{end_index}]: {best_cursor}")

            if last_best_cursor is None:
                # NOTE: Should only execute first time
                last_best_cursor = best_cursor

            elif last_best_cursor != best_cursor:
                # NOTE: Yield whatever the last "best cursor" was,
                #       shrunk up to just before current segment
                yield last_best_cursor.shrink(
                    start_index=last_start_index,
                    end_index=start_index - 1,
                )
                # NOTE: Update our yield variables for next time
                last_start_index = start_index
                last_best_cursor = best_cursor

            # else: last best is also current best, keep iterating until better one is found

        # NOTE: Always yield last best after loop ends, which contain the final part of query
        assert last_best_cursor, "This shouldn't happen best >2 endpoints exist"  # mypy happy
        yield last_best_cursor.shrink(start_index=last_start_index)

    def _experimental_query(
        self,
        query: QueryType,
        engine_to_use: Optional[str] = None,
    ) -> QueryResult:
        if not engine_to_use:
            # Sort by earliest point in cursor window (then by longest coverage if same start)
            # NOTE: We will iterate over this >1 times, so collect our iterator here
            all_cursors = sorted(
                (c for engine in self.engines.values() for c in engine.exec(query)),
                key=lambda c: c.query,
            )

        elif selected_engine := self.engines.get(engine_to_use):
            all_cursors = list(selected_engine.exec(query))

        else:
            raise QueryEngineError(
                f"Query engine `{engine_to_use}` not found. "
                f"Did you mean {' or '.join(self._suggest_engines(engine_to_use))}?"
            )

        logger.debug("Sorted cursors:\n  " + "\n  ".join(map(str, all_cursors)))
        result = QueryResult(
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
        engine_to_use: Optional[str] = None,
    ) -> Iterator[BaseInterfaceModel]:
        """
        Args:
            query (``QueryType``): The type of query to execute
            engine_to_use (Optional[str]): Short-circuit selection logic using
              a specific engine. Defaults is set by performance-based selection logic.

        Raises:
            :class:`~ape.exceptions.QueryEngineError`: When given an invalid or
          inaccessible ``engine_to_use`` value.

        Returns:
            Iterator[``BaseInterfaceModel``]
        """
        if os.environ.get("APE_ENABLE_EXPERIMENTAL_QUERY_BACKEND", False):
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
            estimates = map(lambda qe: (qe, qe.estimate_query(query)), self.engines.values())

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
