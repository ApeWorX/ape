from functools import partial
from typing import Any, Dict, Iterator, Optional

import pandas as pd
from pydantic import BaseModel

from ape.api import BlockAPI, QueryAPI, QueryType
from ape.api.query import BlockQuery, _BaseQuery
from ape.exceptions import ChainError, QueryEngineError
from ape.plugins import clean_plugin_name
from ape.utils import ManagerAccessMixin, cached_property, singledispatchmethod


def get_columns_from_item(query: _BaseQuery, item: BaseModel) -> Dict[str, Any]:
    return {k: v for k, v in item.dict().items() if k in query.columns}


class DefaultQueryProvider(QueryAPI):
    """
    Default implementation of the ape.api.query.QueryAPI
    Allows for the query of blockchain data using connected provider
    """

    @singledispatchmethod
    def estimate_query(self, query: QueryType) -> Optional[int]:

        return None  # can't handle this query

    @estimate_query.register
    def estimate_block_query(self, query: BlockQuery) -> Optional[int]:
        # NOTE: Very loose estimate of 100ms per block
        return (query.stop_block - query.start_block) * 100

    @singledispatchmethod
    def perform_query(self, query: QueryType) -> pd.DataFrame:

        raise QueryEngineError(f"Cannot handle '{type(query)}'.")

    @perform_query.register
    def perform_block_query(self, query: BlockQuery) -> pd.DataFrame:
        blocks_iter = self.query_manager.get_blocks(query.start_block, query.stop_block)
        block_dicts_iter = map(partial(get_columns_from_item, query), blocks_iter)
        return pd.DataFrame(columns=query.columns, data=block_dicts_iter)


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

    def get_blocks(
        self, start_or_stop: int, stop: Optional[int] = None, step: int = 1
    ) -> Iterator[BlockAPI]:
        """
        Iterate over blocks. Works similarly to python ``range()``.

        Raises:
            :class:`~ape.exceptions.ChainError`: When ``stop`` is greater
                than the chain length.
            :class:`~ape.exceptions.ChainError`: When ``stop`` is less
                than ``start_block``.
            :class:`~ape.exceptions.ChainError`: When ``stop`` is less
                than 0.
            :class:`~ape.exceptions.ChainError`: When ``start`` is less
                than 0.

        Args:
            start_or_stop (int): When given just a single value, it is the stop.
              Otherwise, it is the start. This mimics the behavior of ``range``
              built-in Python function.
            stop (Optional[int]): The block number to stop before. Also the total
              number of blocks to get. If not setting a start value, is set by
              the first argument.
            step (Optional[int]): The value to increment by. Defaults to ``1``.
             number of blocks to get. Defaults to the latest block.

        Returns:
            Iterator[:class:`~ape.api.providers.BlockAPI`]
        """

        if stop is None:
            stop = start_or_stop
            start = 0
        else:
            start = start_or_stop

        if stop > len(self.chain_manager.blocks):
            raise ChainError(
                f"'stop={stop}' cannot be greater than the "
                f"chain length ({len(self.chain_manager.blocks)}). "
                f"Use '{self.chain_manager.blocks.poll_blocks.__name__}()' "
                f"to wait for future blocks."
            )
        elif stop < start:
            raise ValueError(f"stop '{stop}' cannot be less than start '{start}'.")
        elif stop < 0:
            raise ValueError(f"start '{start}' cannot be negative.")
        elif start_or_stop < 0:
            raise ValueError(f"stop '{stop}' cannot be negative.")

        for i in range(start, stop, step):
            yield self.chain_manager.blocks._get_block(i)
