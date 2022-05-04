import math
from functools import partial
import itertools
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
from pydantic import BaseModel
from sqlalchemy import create_engine  # type: ignore
from sqlalchemy.sql import text  # type: ignore

from ape.api import QueryAPI, QueryType
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.api.query import AccountQuery, BlockQuery, ContractEventQuery, _BaseQuery
from ape.exceptions import QueryEngineError
from ape.utils import logger, singledispatchmethod

from . import models

TABLE_NAME = {
    BlockQuery: "blocks",
    AccountQuery: "transactions",
    ContractEventQuery: "contract_events",
}


def get_columns_from_item(query: _BaseQuery, item: BaseModel) -> Dict[str, Any]:
    return {k: v for k, v in item.dict().items() if k in query.columns}


class CacheQueryProvider(QueryAPI):
    """
    Default implementation of the ape.api.query.QueryAPI
    Allows for the query of blockchain data using connected provider
    """

    @property
    def database_file(self) -> Path:
        if not self.network_manager.active_provider:
            raise QueryEngineError("Not connected to a network")

        ecosystem_name = self.provider.network.ecosystem.name
        network_name = self.provider.network.name
        if network_name == LOCAL_NETWORK_NAME:
            raise QueryEngineError("Cannot cache local network")

        if "-fork" in network_name:
            network_name = network_name.replace("-fork", "")

        (self.config_manager.DATA_FOLDER / ecosystem_name).mkdir(exist_ok=True)

        return self.config_manager.DATA_FOLDER / ecosystem_name / f"{network_name}.db"

    @property
    def engine(self):
        return create_engine(f"sqlite:///{self.database_file}", pool_pre_ping=True)

    def init_db(self):
        if self.database_file.is_file():
            raise QueryEngineError("Database has already been initialized")

        models.Base.metadata.create_all(bind=self.engine)

    def purge_db(self):
        if not self.database_file.is_file():
            # Add check here to show we have a file that exists
            raise QueryEngineError("Database must be initialized")

        self.database_file.unlink()

    @singledispatchmethod
    def estimate_query(self, query: QueryType) -> Optional[int]:  # type: ignore
        return None  # can't handle this query

    @estimate_query.register
    def estimate_block_query(self, query: BlockQuery) -> Optional[int]:
        try:
            with self.engine.connect() as conn:
                q = conn.execute(
                    text(
                        """
                        SELECT COUNT(*)
                        FROM blocks
                        WHERE blocks.number >= :start_block
                        AND blocks.number <= :stop_block
                        AND blocks.number mod :step = 0
                        """
                    ),
                    start_block=query.start_block,
                    stop_block=query.stop_block,
                    step=query.step,
                )
                number_of_rows = q.rowcount

        except Exception as err:
            # Note: If any error, skip the data from the cache and continue to
            #       query from provider.
            logger.debug(err)
            number_of_rows = 0

        # NOTE: Assume 200 msec to get data from database
        time_to_get_cached_records = 200 if number_of_rows > 0 else 0
        # NOTE: Very loose estimate of 0.75ms per block
        time_to_get_uncached_records = int(
            ((query.stop_block - query.start_block) / query.step - number_of_rows) * 0.75
        )
        return time_to_get_cached_records + time_to_get_uncached_records

    @singledispatchmethod
    def perform_query(self, query: QueryType) -> pd.DataFrame:  # type: ignore
        raise QueryEngineError(f"Cannot handle '{type(query)}'.")

    @perform_query.register
    def perform_block_query(self, query: BlockQuery) -> pd.DataFrame:
        try:
            with self.engine.connect() as conn:
                q = conn.execute(
                    text(
                        """
                        SELECT :columns
                        FROM blocks
                        WHERE blocks.number >= :start_block
                        AND blocks.number <= :stop_block
                        AND blocks.number mod :step = 0
                        """
                    ),
                    columns=",".join(query.columns),
                    start_block=query.start_block,
                    stop_block=query.stop_block,
                    step=query.step,
                )
                cached_records = pd.DataFrame(columns=query.columns, data=q.fetchall())

        except Exception as err:
            # Note: If any error, skip the data from the cache and continue to
            #       query from provider.
            logger.debug(err)
            cached_records = pd.DataFrame(columns=query.columns)

        if len(cached_records) == math.ceil((query.stop_block - query.start_block) / query.step):
            return cached_records

        blocks_iter = map(
            self.provider.get_block,
            # NOTE: the range stop block is a non-inclusive stop.
            #       Where as the query method is an inclusive stop.
            range(query.start_block + len(cached_records), query.stop_block + 1, query.step),
        )

        blocks_iter, blocks_iter_copy = itertools.tee(blocks_iter)
        query_kwargs = query.dict()
        query_kwargs["columns"] = query.all_fields()
        uncached_unfiltered_records = pd.DataFrame(columns=query.all_fields(), data=blocks_iter_copy)
        self.update_cache(BlockQuery(**query_kwargs), uncached_unfiltered_records)
        block_dicts_iter = map(partial(get_columns_from_item, query), blocks_iter)
        return pd.concat(
            [
                cached_records,
                pd.DataFrame(columns=query.columns, data=block_dicts_iter),
            ]
        )

    def update_cache(self, query: QueryType, result: pd.DataFrame):
        # TODO: Add handling of having primary key and potentially
        #  updating table with certain columns
        if set(result.columns) != set(query.all_fields()):
            return  # We do not have all the data to update the database

        try:
            with self.engine.connect() as conn:
                breakpoint()
                result.to_sql(TABLE_NAME[type(query)], conn, if_exists="append", index=False)

        except Exception as err:
            # Note: If any error, skip the data from the cache and continue to
            #       query from provider.
            logger.debug(err)
