from typing import List

import pandas as pd
from pluggy import PluginManager  # type: ignore

from ape.api import Query, QueryAPI
from ape.exceptions import QueryEngineException
from ape.utils import cached_property


class QueryManager:
    """
    A singelton that manages all query sources.

    Args:
        query (``Query``): query to execute

    Returns:

    Usage example::

        chain.blocks.query()
    """

    plugin_manager: PluginManager
    """A reference to the global plugin manager."""

    @cached_property
    def query_engines(self) -> List[QueryAPI]:
        return [engine for _, engine in self.plugin_manager.query_engines]

    def __getitem__(self, engine_name: str) -> QueryAPI:
        """
        Get an engine by name.

        Args:
            engine_name (str): The name of the engine to get.

        Returns:
            :class:`~ape.api.query.QueryAPI`
        """
        if engine_name not in self.plugin_manager.query_engines:
            raise QueryEngineException(engine_name)

        return self.plugin_manager.query_engines[engine_name]

    def query(self, query: Query) -> pd.DataFrame:
        """
        Args:
            query (``Query``): The type of query to execute

        Raises: :class:`~ape.exceptions.QueryEngineException`: When the
            query.engine_to_use is invalid or inaccessible

        Returns:
            pandas.DataFrame
        """

        # Get heuristics from all the query engines to perform this query
        # NOTE: `self.query_engines` should be `cached_property` of loading
        #       `[engine for _, engine in PluginManager.query_engines]`
        estimates = map(lambda qe: (qe, qe.estimate_query(query)), self.query_engines)
        # Ignore query engines that can't perform this query
        valid_estimates = filter(lambda qe: qe[1] is not None, estimates)
        # Find the "best" engine to perform the query
        # NOTE: Sorted by fastest time heuristic
        query_engine, _ = min(valid_estimates, key=lambda qe: qe[1])  # type: ignore
        # Go fetch the result from the engine
        return query_engine.perform_query(query)
