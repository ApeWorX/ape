from pathlib import Path
from typing import Any, List, Optional, Union

import pandas as pd
import sqlalchemy.exc
from sqlalchemy import create_engine  # type: ignore
from sqlalchemy.sql import text  # type: ignore

from ape.api import QueryAPI, QueryType
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.api.query import BlockQuery, BlockTransactionQuery, ContractEventQuery
from ape.exceptions import QueryEngineError
from ape.logging import logger
from ape.utils import singledispatchmethod  # type: ignore

from . import models


class CacheQueryProvider(QueryAPI):
    """
    Default implementation of the ape.api.query.QueryAPI
    Allows for the query of blockchain data using connected provider
    """

    @property
    def database_file(self) -> Optional[Path]:
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

    def _block_query(
        self, query_stmt: str, query: Union[BlockQuery, ContractEventQuery]
    ) -> Union[int, pd.DataFrame]:
        with self.engine.connect() as conn:
            if "COUNT" in query_stmt:
                q = conn.execute(
                    text(query_stmt),
                    start_block=query.start_block,
                    stop_block=query.stop_block,
                    step=query.step,
                )
                return q.rowcount
            elif "SELECT :" in query_stmt:
                q = conn.execute(
                    text(query_stmt),
                    columns=",".join(query.columns),
                    start_block=query.start_block,
                    stop_block=query.stop_block,
                    step=query.step,
                )
                return pd.DataFrame(columns=query.columns, data=q.fetchall())
        raise Exception("SELECT statement improperly set.")

    @singledispatchmethod
    def table(self, query: QueryType):
        raise QueryEngineError("Not a compatible QueryType")

    @table.register
    def block_table(self, query: BlockQuery) -> str:
        return "blocks"

    @table.register
    def transactions_table(self, query: BlockTransactionQuery) -> str:
        return "transactions"

    @table.register
    def contract_events_table(self, query: ContractEventQuery) -> str:
        return "contract_events"

    @singledispatchmethod
    def column(self, query: QueryType) -> str:
        raise QueryEngineError("Not a compatible QueryType")

    @column.register
    def block_column(self, query: BlockQuery) -> str:
        return "number"

    @column.register
    def block_transaction_column(self, query: BlockTransactionQuery) -> str:
        return "block_hash"

    @column.register
    def contract_event_column(self, query: ContractEventQuery) -> str:
        return "block_number"

    @singledispatchmethod
    def cache_query(self, query: QueryType) -> str:
        raise QueryEngineError("Not a compatible QueryType")

    @cache_query.register
    def block_cache_query(self, query: BlockQuery) -> str:
        return "SELECT * FROM blocks WHERE number = :val"

    @cache_query.register
    def block_transaction_cache_query(self, query: BlockTransactionQuery) -> str:
        return "SELECT * FROM transactions WHERE block_hash = :val"

    @cache_query.register
    def contract_event_cache_query(self, query: ContractEventQuery) -> str:
        return "SELECT * FROM contract_events WHERE block_number = :val"

    @singledispatchmethod
    def estimate_query_stmt(self, query: QueryType) -> str:
        raise QueryEngineError("Not a compatible QueryType")

    @estimate_query_stmt.register
    def block_estimate_stmt(self, query: BlockQuery) -> str:
        return """
            SELECT COUNT(*)
            FROM blocks
            WHERE blocks.number >= :start_block
            AND blocks.number <= :stop_block
            AND blocks.number mod :step = 0
        """

    @estimate_query_stmt.register
    def transaction_estimate_stmt(self, query: BlockTransactionQuery) -> str:
        return """
            SELECT COUNT(*)
            FROM transactions
            WHERE transactions.block_id = :block_id
        """

    @estimate_query_stmt.register
    def contract_events_estimate_stmt(self, query: ContractEventQuery) -> str:
        return """
            SELECT COUNT(*)
            FROM contract_events
            WHERE contract_events.block_number >= :start_block
            AND contract_events.block_number <= :stop_block
            AND contract_events.block_number mod :step = 0
        """

    @singledispatchmethod
    def perform_query_stmt(self, query: QueryType) -> str:
        raise QueryEngineError("Not a compatible QueryType")

    @perform_query_stmt.register
    def perform_block_stmt(self, query: BlockQuery) -> str:
        return """
            SELECT :columns
            FROM blocks
            WHERE blocks.number >= :start_block
            AND blocks.number <= :stop_block
            AND blocks.number mod :step = 0
        """

    @perform_query_stmt.register
    def perform_transaction_stmt(self, query: BlockTransactionQuery) -> str:
        return """
            SELECT :columns
            FROM transactions
            WHERE transactions.block_id = :block_id
        """

    @perform_query_stmt.register
    def perform_contract_event_stmt(self, query: ContractEventQuery) -> str:
        return """
            SELECT :columns
            FROM contract_events
            WHERE contract_events.block_number >= :start_block
            AND contract_events.block_number <= :stop_block
            AND contract_events.block_number mod :step = 0
        """

    @singledispatchmethod
    def estimate_query(self, query: QueryType) -> Optional[int]:  # type: ignore
        return None  # can't handle this query

    @estimate_query.register
    def estimate_block_query(self, query: BlockQuery) -> Optional[int]:
        try:
            if (
                self._block_query(self.estimate_query_stmt(query), query)
                == (query.stop_block - query.start_block) // query.step
            ):
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

    @estimate_query.register
    def estimate_block_transaction_query(self, query: BlockTransactionQuery) -> Optional[int]:
        try:
            with self.engine.connect() as conn:
                q = conn.execute(
                    text(self.estimate_query_stmt(query)),
                    block_id=query.block_id,
                )
                if q.rowcount > 0:
                    # NOTE: Assume 200 msec to get data from database
                    return 200
                # Can't handle this query
                return None

        except Exception as err:
            # Note: If any error, skip the data from the cache and continue to
            #       query from provider.
            logger.debug(err)
            return None

    @estimate_query.register
    def estimate_contract_events_query(self, query: ContractEventQuery) -> Optional[int]:
        try:
            if (
                self._block_query(self.estimate_query_stmt(query), query)
                == (query.stop_block - query.start_block) // query.step
            ):
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
        return self._block_query(self.perform_query_stmt(query), query)  # type: ignore

    @perform_query.register
    def perform_transaction_query(self, query: BlockTransactionQuery) -> pd.DataFrame:
        with self.engine.connect() as conn:
            q = conn.execute(
                text(self.perform_query_stmt(query)),
                columns=",".join(query.columns),
                start_block=query.block_id,
            )
            return pd.DataFrame(columns=query.columns, data=q.fetchall())

    @perform_query.register
    def perform_contract_events_query(self, query: ContractEventQuery) -> pd.DataFrame:
        return self._block_query(self.perform_query_stmt(query), query)  # type: ignore

    @singledispatchmethod
    def get_dataframe(self, query: QueryType, result: List[Any]):
        pass

    @get_dataframe.register
    def get_block_dataframe(self, query: BlockQuery, result: List[Any]):
        return pd.DataFrame(
            columns=query.columns,
            data=[val for val in map(lambda val: val.dict(by_alias=False), result)],
        )

    @get_dataframe.register
    def get_transaction_dataframe(self, query: BlockTransactionQuery, result: List[Any]):
        df = pd.DataFrame(
            columns=["receiver", "nonce", "sender"],
            data=[(val.receiver, val.nonce, val.sender) for val in result],
        )
        df["block_hash"] = query.block_id
        if query.columns != ["*"]:
            df = df[[query.columns]]
        return df

    @get_dataframe.register
    def get_contract_event_dataframe(self, query: ContractEventQuery, result: List[Any]):
        return pd.DataFrame(
            columns=query.columns,
            data=[val for val in map(lambda val: val.dict(by_alias=False), result)],
        )

    def update_cache(self, query: QueryType, result: List[Any]) -> None:
        df = self.get_dataframe(query, result)

        try:
            with self.engine.connect() as conn:
                for idx, row in df.iterrows():
                    try:
                        v = conn.execute(
                            text(self.cache_query(query)),
                            column=self.column(query),
                            val=str(row[self.column(query)]),
                        )
                        if [i for i in v]:
                            df = df[df[self.column(query)] != row[self.column(query)]]

                        if df.empty:
                            return

                    except sqlalchemy.exc.OperationalError as err:
                        logger.info(err)
                        df.to_sql(self.table(query), conn, if_exists="append", index=False)
                        return

                df.to_sql(self.table(query), conn, if_exists="append", index=False)

        except Exception as err:
            # Note: If any error, skip the data from the cache and continue to
            #       query from provider.
            logger.info(err)
