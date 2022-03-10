from functools import partial
from typing import Any, Dict, Optional

import pandas as pd
from pydantic import BaseModel

from ape.api import QueryAPI, QueryType
from ape.api.query import BlockQuery, _BaseQuery
from ape.exceptions import QueryEngineError
from ape.plugins import clean_plugin_name
from ape.utils import ManagerAccessMixin, cached_property


def get_columns_from_item(query: _BaseQuery, item: BaseModel) -> Dict[str, Any]:
    return {k: v for k, v in item.dict().items() if k in query.columns}


class DefaultQueryProvider(QueryAPI):
    """
    Default implementation of the ape.api.query.QueryAPI
    Allows for the query of blockchain data using connected provider
    """

    def estimate_query(self, query: QueryType) -> Optional[int]:
        """
        Estimates the time that the query will take as a timestamp

        Args:
            query (``QueryType``): The transaction data you want to query

        Returns:
             Optional[int]: Depends on whether the query can be completed
        """
        if isinstance(query, BlockQuery):
            # NOTE: Very loose estimate of 100ms per block
            return (query.stop_block - query.start_block) * 100

        return None  # can't handle this query

    def perform_query(self, query: QueryType) -> pd.DataFrame:
        """
        Performs a query

        Args:
            query (``QueryType``): The specific transaction data you want to query

        Returns:
            pd.DataFrame: A pandas dataframe
        """
        if isinstance(query, BlockQuery):
            blocks_iter = self.chain_manager.blocks.range(query.start_block, query.stop_block)
            block_dicts_iter = map(partial(get_columns_from_item, query), blocks_iter)
            return pd.DataFrame(columns=query.columns, data=block_dicts_iter)

        raise QueryEngineError(f"Cannot handle '{type(query)}'.")


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

    def query(self, query: QueryType, engine_to_use: Optional[str] = None) -> pd.DataFrame:
        """
        Args:
            query (``QueryType``): The type of query to execute
            engine_to_use (Optional[str]): Short-circuit selection logic using
              a specific engine. Defaults to None.

        Raises: :class:`~ape.exceptions.QueryEngineError`: When given an
            invalid or inaccessible ``engine_to_use`` value.

        Returns:
            pandas.DataFrame
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
