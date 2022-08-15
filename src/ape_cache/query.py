from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import CursorResult  # type: ignore
from sqlalchemy.sql import column, insert, select, text
from sqlalchemy.sql.expression import Insert, TextClause

from ape.api import QueryAPI, QueryType
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.api.query import BaseInterfaceModel, BlockQuery, BlockTransactionQuery, ContractEventQuery
from ape.exceptions import QueryEngineError
from ape.logging import logger
from ape.utils import singledispatchmethod

from . import models
from .models import Blocks, ContractEvents, Transactions


class CacheQueryProvider(QueryAPI):
    """
    Default implementation of the :class:`~ape.api.query.QueryAPI`.
    Allows for the query of blockchain data using a connected provider.
    """

    # Database management
    def get_database_file(self, ecosystem_name: str, network_name: str) -> Path:
        """
        Allows us to figure out what the file *will be*, mostly used for database management.
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
        database_file.parent.mkdir(exist_ok=True, parents=True)

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
        Returns a connection for the currently active network.
        NOTE: Creates a database if it doesn't exist.
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

        except Exception as e:
            logger.warning(f"Unhandled exception when querying:\n{e}")
            return None

    # Estimate query
    @singledispatchmethod
    def estimate_query_clause(self, query: QueryType) -> TextClause:
        raise QueryEngineError(
            """
            Not a compatible QueryType. For more details see our docs
            https://docs.apeworx.io/ape/stable/methoddocs/exceptions.html#ape.exceptions.QueryEngineError
            """
        )

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
    WHERE transactions.block_hash = :block_hash
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
    def compute_estimate(self, query: QueryType, result: CursorResult) -> Optional[int]:
        return None  # can't handle this query

    @compute_estimate.register
    def compute_estimate_block_query(
        self,
        query: BlockQuery,
        result: CursorResult,
    ) -> Optional[int]:
        if result.first()[0] == (1 + query.stop_block - query.start_block) // query.step:
            # NOTE: Assume 200 msec to get data from database
            return 200

        # Can't handle this query
        # TODO: Allow partial queries
        return None

    @compute_estimate.register
    def compute_estimate_block_transaction_query(
        self,
        query: BlockTransactionQuery,
        result: CursorResult,
    ) -> Optional[int]:
        if result.first()[0] > 0:
            # NOTE: Assume 200 msec to get data from database
            return 200

        # Can't handle this query
        return None

    @compute_estimate.register
    def compute_estimate_contract_events_query(
        self,
        query: ContractEventQuery,
        result: CursorResult,
    ) -> Optional[int]:
        if result.first()[0] == (query.stop_block - query.start_block) // query.step:
            # NOTE: Assume 200 msec to get data from database
            return 200

        # Can't handle this query
        # TODO: Allow partial queries
        return None

    def estimate_query(self, query: QueryType) -> Optional[int]:
        try:
            with self.database_connection as conn:
                result = conn.execute(self.estimate_query_clause(query))

                if not result:
                    return None

                return self.compute_estimate(query, result)
        except QueryEngineError as err:
            logger.warning(f"Cannot perform query on cache database: {err}")
            return None

    # Fetch data
    @singledispatchmethod
    def perform_query_clause(self, query: QueryType) -> TextClause:
        raise QueryEngineError(
            "Not a compatible QueryType. For more details see our docs "
            "https://docs.apeworx.io/ape/stable/methoddocs/"
            "exceptions.html#ape.exceptions.QueryEngineError"
        )

    @perform_query_clause.register
    def perform_block_clause(self, query: BlockQuery) -> TextClause:
        return (
            select([column(c) for c in query.columns])
            .where(Blocks.number >= query.start_block)
            .where(Blocks.number <= query.stop_block)
            .where(Blocks.number % query.step == 0)
        )

    @perform_query_clause.register
    def perform_transaction_clause(self, query: BlockTransactionQuery) -> TextClause:
        return select([column(c) for c in query.columns]).where(
            Transactions.block_hash == query.block_id
        )

    @perform_query_clause.register
    def perform_contract_event_clause(self, query: ContractEventQuery) -> TextClause:
        return (
            select([column(c) for c in query.columns])
            .where(ContractEvents.block_number >= query.start_block)
            .where(ContractEvents.block_number <= query.stop_block)
            .where(ContractEvents.block_number % query.step == 0)
        )

    @singledispatchmethod
    def perform_query(self, query: QueryType) -> Optional[List]:  # type: ignore
        try:
            with self.database_connection as conn:
                result = conn.execute(self.perform_query_clause(query))

                if not result:
                    # NOTE: Should be unreachable if estimated correctly
                    raise QueryEngineError(f"Could not perform query:\n{query}")

                breakpoint()
                for row in result:
                    yield {key: value for (key, value) in row.items()}
                # return [QueryType({key: value for (key, value) in row.items()} for row in result)]
                # for row in result:
                #     yield {key: value for (key, value) in row.items()}

        except QueryEngineError as err:
            logger.error(f"Database not initiated: {str(err)}")

    @singledispatchmethod
    def cache_update_clause(self, query: QueryType) -> Optional[Insert]:
        pass  # Can't cache this query

    @cache_update_clause.register
    def cache_update_block_clause(self, query: BlockQuery) -> Optional[Insert]:
        return insert(Blocks)  # type: ignore

    @cache_update_clause.register
    def cache_update_block_txns_clause(self, query: BlockTransactionQuery) -> Optional[Insert]:
        return insert(Transactions)  # type: ignore

    @cache_update_clause.register
    def cache_update_events_clause(self, query: ContractEventQuery) -> Optional[Insert]:
        return insert(ContractEvents)  # type: ignore

    @singledispatchmethod
    def get_cache_data(
        self, query: QueryType, result: Iterator[BaseInterfaceModel]
    ) -> Optional[List[Dict[str, Any]]]:
        raise QueryEngineError(
            """
            Not a compatible QueryType. For more details see our docs
            https://docs.apeworx.io/ape/stable/methoddocs/exceptions.html#ape.exceptions.QueryEngineError
            """
        )

    @get_cache_data.register
    def get_block_cache_data(
        self, query: BlockQuery, result: Iterator[BaseInterfaceModel]
    ) -> Optional[List[Dict[str, Any]]]:
        return [m.dict(by_alias=False) for m in result]

    @get_cache_data.register
    def get_block_txns_data(
        self, query: BlockTransactionQuery, result: Iterator[BaseInterfaceModel]
    ) -> Optional[List[Dict[str, Any]]]:
        new_result = []
        table_columns = [c.key for c in Transactions.__table__.columns]  # type: ignore
        for val in [m for m in result]:
            new_dict = {k: v for k, v in val.dict(by_alias=False).items() if k in table_columns}
            for col in table_columns:
                if col == "txn_hash":
                    new_dict["txn_hash"] = val.txn_hash  # type: ignore
                elif col == "sender":
                    new_dict["sender"] = new_dict["sender"].encode()
                elif col == "receiver" and "receiver" in new_dict:
                    new_dict["receiver"] = new_dict["receiver"].encode()
                elif col == "receiver" and "receiver" not in new_dict:
                    new_dict["receiver"] = bytes()
                elif col == "block_hash":
                    new_dict["block_hash"] = query.block_id
                elif col == "signature":
                    new_dict["signature"] = val.signature.encode_rsv()  # type: ignore
                elif col not in new_dict:
                    new_dict[col] = None
            new_result.append(new_dict)
        return new_result

    @get_cache_data.register
    def get_cache_events_data(
        self, query: ContractEventQuery, result: Iterator[BaseInterfaceModel]
    ) -> Optional[List[Dict[str, Any]]]:
        return [m.dict(by_alias=False) for m in result]

    def update_cache(self, query: QueryType, result: Iterator[BaseInterfaceModel]):
        clause = self.cache_update_clause(query)
        if str(clause):
            logger.debug(f"Caching query: {query}")
            with self.database_connection as conn:
                try:
                    conn.execute(
                        clause.values(  # type: ignore
                            self.get_cache_data(query, result)
                        ).prefix_with("OR IGNORE")
                    )

                except QueryEngineError as err:
                    logger.warning(f"Database corruption: {err}")
