from pathlib import Path
from typing import Any, Iterator, Optional

import pandas as pd
import sqlalchemy.exc
from sqlalchemy import create_engine  # type: ignore
from sqlalchemy.sql import text  # type: ignore

from ape.api import QueryAPI, QueryType
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.api.query import AccountTransactionQuery, BlockQuery, ContractEventQuery
from ape.exceptions import QueryEngineError
from ape.logging import logger
from ape.utils import singledispatchmethod  # type: ignore

from . import models

TABLE_NAME = {
    BlockQuery: "blocks",
    AccountTransactionQuery: "transactions",
    ContractEventQuery: "contract_events",
}


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
            # Note: no need to cache local network, no use for data
            raise QueryEngineError("Cannot cache local network")

        if "-fork" in network_name:
            # Note: send query to pull from upstream
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
                if q.rowcount == query.stop_block - query.start_block:
                    # NOTE: Assume 200 msec to get data from database
                    return 200
                # Can't handle this query
                # TODO: Allow partial queries
                return None

        except Exception as err:
            # Note: If any error, skip the data from the cache and continue to
            #       query from provider.
            logger.debug(err)
            return None

    @singledispatchmethod
    def perform_query(self, query: QueryType) -> pd.DataFrame:  # type: ignore
        raise QueryEngineError(f"Cannot handle '{type(query)}'.")

    @perform_query.register
    def perform_block_query(self, query: BlockQuery) -> pd.DataFrame:
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
            return pd.DataFrame(columns=query.columns, data=q.fetchall())

    def update_cache(self, query: QueryType, result: Iterator[Any]) -> None:  # type: ignore
        data = map(lambda val: val.dict(by_alias=False), result)
        df = pd.DataFrame(columns=query.columns, data=[val for val in data])

        try:
            with self.engine.connect() as conn:
                for idx, row in df.iterrows():
                    try:
                        v = conn.execute(
                            text(
                                """
                                SELECT * FROM blocks
                                WHERE blocks.number = :number
                                """
                            ),
                            number=row["number"],
                        )
                        if [i for i in v]:
                            df = df[df["number"] != row["number"]]

                    except sqlalchemy.exc.OperationalError as err:
                        logger.info(err)
                        df.to_sql(TABLE_NAME[type(query)], conn, if_exists="append", index=False)
                        return

                df.to_sql(TABLE_NAME[type(query)], conn, if_exists="append", index=False)

        except Exception as err:
            # Note: If any error, skip the data from the cache and continue to
            #       query from provider.
            logger.debug(err)
