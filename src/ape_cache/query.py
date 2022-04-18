from functools import partial
import pandas as pd
from pydantic import BaseModel
from typing import Dict, Any, Optional
from pathlib import Path

from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from ape.api import QueryAPI, QueryType
from ape.exceptions import QueryEngineError
from ape.utils import singledispatchmethod, cached_property
from ape.api.query import BlockQuery, _BaseQuery


def get_columns_from_item(query: _BaseQuery, item: BaseModel) -> Dict[str, Any]:
    return {k: v for k, v in item.dict().items() if k in query.columns}


class CacheQueryProvider(QueryAPI):
    """
    Default implementation of the ape.api.query.QueryAPI
    Allows for the query of blockchain data using connected provider
    """

    @property
    def database_file(self) -> Path:
        return self.config_manager.DATA_FOLDER / "cache.db"

    @cached_property
    def engine(self):
        return create_engine(f"sqlite://{self.database_file}", pool_pre_ping=True)

    @cached_property
    def session(self):
        return sessionmaker(autocommit=False, autoflush=False, bind=self.engine)

    @contextmanager
    def db(self):
        db = self.session()
        try:
            yield db
        finally:
            db.close()

    @singledispatchmethod
    def estimate_query(self, query: QueryType) -> Optional[int]:
        return None  # can't handle this query

    @estimate_query.register
    def estimate_block_query(self, query: BlockQuery) -> Optional[int]:
        with self.db() as db:
            q = db.execute("SELECT COUNT(*) FROM blocks")
            if q == (query.stop_block - query.start_block):
                # I can use the cache database
                return 50  # msec, assume static amount of time to fulfil
            # else: can't use the cache, fall through to brute force provider calls

        # NOTE: Very loose estimate of 100ms per block
        return (query.stop_block - query.start_block) * 100

    @singledispatchmethod
    def perform_query(self, query: QueryType) -> pd.DataFrame:

        raise QueryEngineError(f"Cannot handle '{type(query)}'.")

    @perform_query.register
    def perform_block_query(self, query: BlockQuery) -> pd.DataFrame:
        with self.db() as db:
            q = db.execute("SELECT COUNT(*) FROM blocks")
            if q > 0:
                return pd.Dataframe("SELECT * FROM blocks")
            #else: fall through to brute force query
        blocks_iter = map(
            self.provider.get_block,
            # NOTE: the range stop block is a non-inclusive stop.
            #       Where as the query method is an inclusive stop.
            range(query.start_block, query.stop_block + 1),
        )
        block_dicts_iter = map(partial(get_columns_from_item, query), blocks_iter)
        return pd.DataFrame(columns=query.columns, data=block_dicts_iter)

    def update_cache(self, query: QueryType, result: pd.DataFrame):
        with self.db() as db:
            breakpoint()
            result.to_sql("blocks", db.connection(), if_exists="replace")
