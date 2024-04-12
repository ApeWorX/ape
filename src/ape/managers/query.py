import difflib
import time
from itertools import tee
from typing import Dict, Iterator, Optional

from ape.api import QueryAPI, QueryType, ReceiptAPI, TransactionAPI
from ape.api.query import (
    AccountTransactionQuery,
    BaseInterfaceModel,
    BlockQuery,
    BlockTransactionQuery,
    ContractCreation,
    ContractCreationQuery,
    ContractEventQuery,
)
from ape.contracts.base import ContractLog, LogFilter
from ape.exceptions import QueryEngineError
from ape.logging import logger
from ape.plugins import clean_plugin_name
from ape.types.address import AddressType
from ape.utils import ManagerAccessMixin, cached_property, singledispatchmethod


class DefaultQueryProvider(QueryAPI):
    """
    Default implementation of the :class:`~ape.api.query.QueryAPI`.
    Allows for the query of blockchain data using connected provider.
    """

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
    def estimate_contract_creation_query(self, query: ContractCreationQuery) -> int:
        # NOTE: Extremely expensive query, involves binary search of all blocks in a chain
        #       Very loose estimate of 5s per transaction for this query.
        return 5000

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
    def perform_contract_creation_query(
        self, query: ContractCreationQuery
    ) -> Iterator[ContractCreation]:
        def find_creation_block(lo, hi):
            # perform a binary search to find where the contract code appeared
            # takes log2(height), doesn't work with contracts that have been reinit.
            while hi - lo > 1:
                mid = (lo + hi) // 2
                code = self.provider.get_code(query.contract, block_id=mid)
                if not code:
                    lo = mid
                else:
                    hi = mid

            if self.provider.get_code(query.contract, block_id=hi):
                return hi

        # if it doesn't have code at head, skip the search
        if not self.provider.get_code(query.contract):
            return None

        deploy_block = find_creation_block(0, self.chain_manager.blocks.height)
        deploy_block_traces = self.provider._make_request(
            "trace_replayBlockTransactions", [deploy_block, ["trace"]]
        )

        # iterate over transaction traces in a block to find the deploy transaction
        # this method also supports contract factories
        for tx in deploy_block_traces:
            for trace in tx["trace"]:
                if (
                    "error" not in trace
                    and trace["type"] == "create"
                    and trace["result"]["address"] == query.contract.lower()
                ):
                    receipt = self.chain_manager.get_receipt(tx["transactionHash"])
                    creator = self.conversion_manager.convert(trace["action"]["from"], AddressType)
                    yield ContractCreation(
                        receipt=receipt,
                        deployer=receipt.sender,
                        factory=creator if creator != receipt.sender else None,
                        deploy_block=deploy_block,
                    )

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


class QueryManager(ManagerAccessMixin):
    """
    A singleton that manages query engines and performs queries.

    Args:
        query (``QueryType``): query to execute

    Usage example::

         biggest_block_size = chain.blocks.query("size").max()
    """

    @cached_property
    def engines(self) -> Dict[str, QueryAPI]:
        """
        A dict of all :class:`~ape.api.query.QueryAPI` instances across all
        installed plugins.

        Returns:
            dict[str, :class:`~ape.api.query.QueryAPI`]
        """

        engines: Dict[str, QueryAPI] = {"__default__": DefaultQueryProvider()}

        for plugin_name, engine_class in self.plugin_manager.query_engines:
            engine_name = clean_plugin_name(plugin_name)
            engines[engine_name] = engine_class()  # type: ignore

        return engines

    def _suggest_engines(self, engine_selection):
        return difflib.get_close_matches(engine_selection, list(self.engines), cutoff=0.6)

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

        Raises: :class:`~ape.exceptions.QueryEngineError`: When given an invalid or
          inaccessible ``engine_to_use`` value.

        Returns:
            Iterator[``BaseInterfaceModel``]
        """

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
