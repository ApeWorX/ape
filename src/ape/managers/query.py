from typing import TYPE_CHECKING, Dict, Optional

import pandas as pd

from ape.api import QueryAPI, QueryType
from ape.exceptions import QueryEngineError
from ape.plugins import clean_plugin_name
from ape.utils import cached_property

if TYPE_CHECKING:
    from ape.managers.networks import NetworkManager
    from ape.plugins import PluginManager


class QueryManager:
    """
    A singleton that manages query engines and performs queries.

    Args:
        query (``QueryType``): query to execute

    Usage example::

         biggest_block_size = chain.blocks.query("size").max()
    """

    plugin_manager: "PluginManager"
    """A reference to the global plugin manager."""

    network_manager: "NetworkManager"
    """A reference to the global network manager."""

    @cached_property
    def engines(self) -> Dict[str, QueryAPI]:
        """
        A dict of all :class:`~ape.api.query.QueryAPI` instances across all
        installed plugins.

        Returns:
            dict[str, :class:`~ape.api.query.QueryAPI`]
        """

        engines = {}
        for plugin_name, (engine_class,) in self.plugin_manager.query_engines:
            engine_name = clean_plugin_name(plugin_name)
            engines[engine_name] = engine_class(network_manager=self.network_manager)

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

            return self.engines[engine_to_use].perform_query(query)

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
        return engine.perform_query(query)
