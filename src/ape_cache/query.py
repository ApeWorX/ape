from pathlib import Path
from typing import Iterator, Optional

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.engine import CursorResult  # type: ignore
from sqlalchemy.sql import text
from sqlalchemy.sql.expression import TextClause

from ape.api import QueryAPI, QueryType
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.api.query import BaseInterfaceModel, BlockQuery, BlockTransactionQuery, ContractEventQuery
from ape.exceptions import QueryEngineError
from ape.logging import logger
from ape.utils import singledispatchmethod  # type: ignore

from . import models


class CacheQueryProvider(QueryAPI):
    """
    Default implementation of the ape.api.query.QueryAPI
    Allows for the query of blockchain data using connected provider
    """

    # Database management
    def get_database_file(self, ecosystem_name: str, network_name: str) -> Path:
        """
        Let's us figured out what the file *will be*, mostly used for database management
        """

        if network_name == LOCAL_NETWORK_NAME:
            # NOTE: no need to cache local network, no use for data
            raise QueryEngineError("Cannot cache local data")

        if "-fork" in network_name:
            # NOTE: send query to pull from upstream
            network_name = network_name.replace("-fork", "")

        return self.config_manager.DATA_FOLDER / ecosystem_name / network_name / "cache.db"

    def get_sqlite_uri(self, database_file: Path) -> str:
        return f"sqlite:///{database_file}"

    def init_database(self, ecosystem_name: str, network_name: str):
        database_file = self.get_database_file(ecosystem_name, network_name)
        if database_file.is_file():
            raise QueryEngineError("Database has already been initialized")

        # NOTE: Make sure database folder location has been created
        database_file.parent.parent.mkdir(exist_ok=True)
        database_file.parent.mkdir(exist_ok=True)

        models.Base.metadata.create_all(  # type: ignore
            bind=create_engine(self.get_sqlite_uri(database_file), pool_pre_ping=True)
        )

    def purge_database(self, ecosystem_name: str, network_name: str):
        database_file = self.get_database_file(ecosystem_name, network_name)
        if not database_file.is_file():
            raise QueryEngineError("Database must be initialized")

        database_file.unlink()

    # Operations
    @property
    def database_connection(self):
        """
        Gets the currently active network's database, for actual usage
        NOTE: Makes the database if it doesn't actually exist
        """

        if not self.network_manager.active_provider:
            raise QueryEngineError("Not connected to a provider")

        ecosystem_name = self.provider.network.ecosystem.name
        network_name = self.provider.network.name

        database_file = self.get_database_file(ecosystem_name, network_name)
        if not database_file.is_file():
            raise QueryEngineError("Database has not been initialized")

        try:
            sqlite_uri = self.get_sqlite_uri(database_file)
            return create_engine(sqlite_uri, pool_pre_ping=True).connect()

        except QueryEngineError as e:
            logger.debug(f"Exception when querying:\n{e}")
            return None

        # TODO: Are there any other errors to handle?
        except Exception as e:
            logger.warning(f"Unhandled exception when querying:\n{e}")
            return None

    # Estimate query
    @singledispatchmethod
    def estimate_query_clause(self, query: QueryType) -> TextClause:
        raise QueryEngineError("Not a compatible QueryType")

    @estimate_query_clause.register
    def block_estimate_query_clause(self, query: BlockQuery) -> TextClause:
        return text(
            """
    SELECT COUNT(*)
    FROM blocks
    WHERE blocks.number >= :start_block
    AND blocks.number <= :stop_block
    AND blocks.number % :step = 0
        """
        ).bindparams(start_block=query.start_block, stop_block=query.stop_block, step=query.step)

    @estimate_query_clause.register
    def transaction_estimate_query_clause(self, query: BlockTransactionQuery) -> TextClause:
        return text(
            """
    SELECT COUNT(*)
    FROM transactions
    WHERE transactions.block_hash = :block_id
        """
        ).bindparams(block_hash=query.block_id)

    @estimate_query_clause.register
    def contract_events_estimate_query_clause(self, query: ContractEventQuery) -> TextClause:
        return text(
            """
    SELECT COUNT(*)
    FROM contract_events
    WHERE contract_events.block_number >= :start_block
    AND contract_events.block_number <= :stop_block
    AND contract_events.block_number % :step = 0
        """
        ).bindparams(start_block=query.start_block, stop_block=query.stop_block, step=query.step)

    @singledispatchmethod
    def compute_estimate(self, result: CursorResult, query: QueryType) -> Optional[int]:
        return None  # can't handle this query

    @compute_estimate.register
    def compute_estimate_block_query(
        self, result: CursorResult, query: BlockQuery
    ) -> Optional[int]:
        if result.rowcount == (query.stop_block - query.start_block) // query.step:
            # NOTE: Assume 200 msec to get data from database
            return 200

        # Can't handle this query
        # TODO: Allow partial queries
        return None

    @compute_estimate.register
    def compute_estimate_block_transaction_query(
        self,
        result: CursorResult,
        query: BlockTransactionQuery,
    ) -> Optional[int]:
        if result.rowcount > 0:
            # NOTE: Assume 200 msec to get data from database
            return 200

        # Can't handle this query
        return None

    @compute_estimate.register
    def compute_estimate_contract_events_query(
        self,
        result: CursorResult,
        query: ContractEventQuery,
    ) -> Optional[int]:
        if result.rowcount == (query.stop_block - query.start_block) // query.step:
            # NOTE: Assume 200 msec to get data from database
            return 200

        # Can't handle this query
        # TODO: Allow partial queries
        return None

    def estimate_query(self, query: QueryType) -> Optional[int]:
        with self.database_connection as conn:
            result = conn.execute(self.estimate_query_clause(query))

            if not result:
                return None

            return self.compute_estimate(result, query)

    # Fetch data
    @singledispatchmethod
    def perform_query_clause(self, query: QueryType) -> TextClause:
        raise QueryEngineError("Not a compatible QueryType")

    @perform_query_clause.register
    def perform_block_clause(self, query: BlockQuery) -> TextClause:
        return text(
            """
    SELECT :columns
    FROM blocks
    WHERE blocks.number >= :start_block
    AND blocks.number <= :stop_block
    AND blocks.number % :step = 0
        """
        ).bindparams(
            columns=",".join(query.columns),
            start_block=query.start_block,
            stop_block=query.stop_block,
            step=query.step,
        )

    @perform_query_clause.register
    def perform_transaction_clause(self, query: BlockTransactionQuery) -> TextClause:
        return text(
            """
    SELECT :columns
    FROM transactions
    WHERE transactions.block_hash = :block_id
        """
        ).bindparams(columns=",".join(query.columns), block_id=query.block_id)

    @perform_query_clause.register
    def perform_contract_event_clause(self, query: ContractEventQuery) -> TextClause:
        return text(
            """
    SELECT :columns
    FROM contract_events
    WHERE contract_events.block_number >= :start_block
    AND contract_events.block_number <= :stop_block
    AND contract_events.block_number % :step = 0
        """
        ).bindparams(
            columns=",".join(query.columns),
            start_block=query.start_block,
            stop_block=query.stop_block,
            step=query.step,
        )

    def perform_query(self, query: QueryType) -> pd.DataFrame:
        with self.database_connection as conn:
            result = conn.execute(self.perform_query_clause(query))

            if not result:
                # NOTE: Should be unreachable if estimated correctly
                raise QueryEngineError(f"Could not perform query:\n{query}")

            # TODO: Fix this, should return an iterator
            return pd.DataFrame(columns=query.columns, data=result.fetchall())

    @singledispatchmethod
    def cache_update_clause(self, query: QueryType) -> Optional[TextClause]:
        pass  # Can't cache this query

    @cache_update_clause.register
    def cache_update_block_clause(self, query: BlockQuery) -> Optional[TextClause]:
        return text("INSERT INTO blocks")

    @cache_update_clause.register
    def cache_update_block_txns_clause(self, query: BlockTransactionQuery) -> Optional[TextClause]:
        return text("INSERT INTO transactions")

    @cache_update_clause.register
    def cache_update_events_clause(self, query: ContractEventQuery) -> Optional[TextClause]:
        return text("INSERT INTO contract_events")

    def update_cache(self, query: QueryType, result: Iterator[BaseInterfaceModel]):
        clause = self.cache_update_clause(query)
        if clause:
            logger.debug(f"Caching query: {query}")
            with self.database_connection as conn:
                conn.execute(
                    clause.on_conflict_do_nothing(),  # type: ignore
                    [m.dict() for m in result],
                )
