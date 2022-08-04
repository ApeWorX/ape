from typing import Dict, Iterator, Optional

from ape.api import QueryAPI, QueryType
from ape.api.query import BlockQuery, BlockTransactionQuery, ContractEventQuery
from ape.contracts.base import ContractLog, LogFilter
from ape.exceptions import QueryEngineError
from ape.plugins import clean_plugin_name
from ape.utils import ManagerAccessMixin, cached_property, singledispatchmethod


class DefaultQueryProvider(QueryAPI):
    """
    Default implementation of the ape.api.query.QueryAPI
    Allows for the query of blockchain data using connected provider
    """

    @singledispatchmethod
    def estimate_query(self, query: QueryType) -> Optional[int]:  # type: ignore

        return None  # can't handle this query

    @estimate_query.register
    def estimate_block_query(self, query: BlockQuery) -> Optional[int]:
        # NOTE: Very loose estimate of 100ms per block
        return (query.stop_block - query.start_block) * 100

    @estimate_query.register
    def estimate_block_transaction_query(self, query: BlockTransactionQuery) -> int:

        return 100

    @estimate_query.register
    def estimate_contract_events_query(self, query: ContractEventQuery) -> int:
        # NOTE: Very loose estimate of 100ms per block for this query.
        return 100

    @singledispatchmethod
    def perform_query(self, query: QueryType) -> Iterator:  # type: ignore
        raise QueryEngineError(f"Cannot handle '{type(query)}'.")

    @perform_query.register
    def perform_block_query(self, query: BlockQuery) -> Iterator:
        return map(
            self.provider.get_block,
            # NOTE: the range stop block is a non-inclusive stop.
            #       Where as the query method is an inclusive stop.
            range(query.start_block, query.stop_block + 1, query.step),
        )

    @perform_query.register
    def perform_block_transaction_query(self, query: BlockTransactionQuery) -> Iterator:
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

        for plugin_name, (engine_class,) in self.plugin_manager.query_engines:
            engine_name = clean_plugin_name(plugin_name)
            engines[engine_name] = engine_class()

        return engines

    def query(self, query: QueryType, engine_to_use: Optional[str] = None) -> Iterator[QueryAPI]:
        """
        Args:
            query (``QueryType``): The type of query to execute
            engine_to_use (Optional[str]): Short-circuit selection logic using
              a specific engine. Defaults to None.

        Raises: :class:`~ape.exceptions.QueryEngineError`: When given an
            invalid or inaccessible ``engine_to_use`` value.

        Returns:
            Iterator[QueryAPI]
        """
        if engine_to_use:
            if engine_to_use not in self.engines:
                raise QueryEngineError(f"Query engine `{engine_to_use}` not found.")

            engine = self.engines[engine_to_use]

        else:
            # Get heuristics from all the query engines to perform this query
            estimates = map(lambda qe: (qe, qe.estimate_query(query)), self.engines.values())

            # Ignore query engines that can't perform this query
            valid_estimates = filter(lambda qe: qe[1] is not None, estimates)

            try:
                # Find the "best" engine to perform the query
                # NOTE: Sorted by fastest time heuristic
                engine, _ = min(valid_estimates, key=lambda qe: qe[1])  # type: ignore
            except ValueError as e:
                raise QueryEngineError("No query engines are available.") from e

        # Go fetch the result from the engine
        result = engine.perform_query(query)

        # Update any caches
        for engine in self.engines.values():
            engine.update_cache(query, result)

        return result
