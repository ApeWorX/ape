"""
sub-class the QueryAPI
move the default_query_provider here
Some refactoring that has to be done

2nd step:
Third method added to QueryAPI (update_cache) defaults to doing nothing
override QueryAPI.update_cache
start pushing queries to be on_disk (sqlite)
push the sqlite database to the data folder
update the first two methods to first query the database, if exists, respond with data from
that databases, else go to provider to get raw data

Research the database schema
"""
import pandas as pd
from pydantic import BaseModel
from typing import Dict, Any, Optional

from ape.api import QueryAPI, QueryType
from ape.utils import ManagerAccessMixin, cached_property, singledispatchmethod
from ape.api.query import BlockQuery, _BaseQuery


def get_columns_from_item(query: _BaseQuery, item: BaseModel) -> Dict[str, Any]:
    return {k: v for k, v in item.dict().items() if k in query.columns}


class CacheQueryProvider(QueryAPI):
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
        blocks_iter = map(
            self.provider.get_block,
            # NOTE: the range stop block is a non-inclusive stop.
            #       Where as the query method is an inclusive stop.
            range(query.start_block, query.stop_block + 1),
        )
        block_dicts_iter = map(partial(get_columns_from_item, query), blocks_iter)
        return pd.DataFrame(columns=query.columns, data=block_dicts_iter)
