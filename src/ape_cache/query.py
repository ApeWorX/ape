from collections.abc import Iterator
from functools import singledispatchmethod
from pathlib import Path
from typing import Any, Optional, cast

from sqlalchemy import create_engine, func
from sqlalchemy.engine import CursorResult
from sqlalchemy.sql import column, insert, select
from sqlalchemy.sql.expression import Insert, Select

from ape.api.providers import BlockAPI
from ape.api.query import (
    BaseInterfaceModel,
    BlockQuery,
    BlockTransactionQuery,
    ContractEventQuery,
    QueryAPI,
    QueryType,
)
from ape.api.transactions import TransactionAPI
from ape.exceptions import QueryEngineError
from ape.logging import logger
from ape.types.events import ContractLog
from ape.utils.misc import LOCAL_NETWORK_NAME

from . import models
from .models import Blocks, ContractEvents, Transactions


class CacheQueryProvider(QueryAPI):
    """
    Default implementation of the :class:`~ape.api.query.QueryAPI`.
    Allows for the query of blockchain data using a connected provider.
    """

    # Class var for tracking if we detect a scenario where the cache db isn't working
    database_bypass = False

    def _get_database_file(self, ecosystem_name: str, network_name: str) -> Path:
        """
        Allows us to figure out what the file *will be*, mostly used for database management.

        Args:
            ecosystem_name (str): Name of the ecosystem to store data for (ex: ethereum)
            network_name (str): name of the network to store data for (ex: mainnet)

        Raises:
            :class:`~ape.exceptions.QueryEngineError`: If a local network is provided.
        """

        if network_name == LOCAL_NETWORK_NAME:
            # NOTE: no need to cache local network, no use for data
            raise QueryEngineError("Cannot cache local data")

        if "-fork" in network_name:
            # NOTE: send query to pull from upstream
            network_name = network_name.replace("-fork", "")

        return self.config_manager.DATA_FOLDER / ecosystem_name / network_name / "cache.db"

    def _get_sqlite_uri(self, database_file: Path) -> str:
        """
        Gets a string for the sqlite db URI.

        Args:
            database_file (`pathlib.Path`): A path to the database file.

        Returns:
            str
        """

        return f"sqlite:///{database_file}"

    def init_database(self, ecosystem_name: str, network_name: str):
        """
        Initialize the SQLite database for caching of provider data.

        Args:
            ecosystem_name (str): Name of the ecosystem to store data for (ex: ethereum)
            network_name (str): name of the network to store data for (ex: mainnet)

        Raises:
            :class:`~ape.exceptions.QueryEngineError`: When the database has not been initialized
        """

        database_file = self._get_database_file(ecosystem_name, network_name)
        if database_file.is_file():
            raise QueryEngineError("Database has already been initialized")

        # NOTE: Make sure database folder location has been created
        database_file.parent.mkdir(exist_ok=True, parents=True)

        models.Base.metadata.create_all(  # type: ignore
            bind=create_engine(self._get_sqlite_uri(database_file), pool_pre_ping=True)
        )

    def purge_database(self, ecosystem_name: str, network_name: str):
        """
        Removes the SQLite database file from disk.

        Args:
            ecosystem_name (str): Name of the ecosystem to store data for (ex: ethereum)
            network_name (str): name of the network to store data for (ex: mainnet)

        Raises:
            :class:`~ape.exceptions.QueryEngineError`: When the database has not been initialized
        """

        database_file = self._get_database_file(ecosystem_name, network_name)
        if not database_file.is_file():
            raise QueryEngineError("Database must be initialized")

        database_file.unlink()

    @property
    def database_connection(self):
        """
        Returns a connection for the currently active network.

        **NOTE**: Creates a database if it doesn't exist.

        Raises:
            :class:`~ape.exceptions.QueryEngineError`: If you are not connected to a provider,
                or if the database has not been initialized.

        Returns:
            Optional[`sqlalchemy.engine.Connection`]
        """
        if self.provider.network.is_local:
            return None

        if not self.network_manager.active_provider:
            raise QueryEngineError("Not connected to a provider")

        database_file = self._get_database_file(
            self.provider.network.ecosystem.name, self.provider.network.name
        )

        if not database_file.is_file():
            # NOTE: Raising `info` here hints user that they can initialize the cache db
            logger.info("`ape-cache` database has not been initialized")
            self.database_bypass = True
            return None

        try:
            sqlite_uri = self._get_sqlite_uri(database_file)
            return create_engine(sqlite_uri, pool_pre_ping=True).connect()

        except QueryEngineError as e:
            logger.debug(f"Exception when querying:\n{e}")
            return None

        except Exception as e:
            logger.warning(f"Unhandled exception when querying:\n{e}")
            self.database_bypass = True
            return None

    @singledispatchmethod
    def _estimate_query_clause(self, query: QueryType) -> Select:
        """
        A singledispatchmethod that returns a select statement.

        Args:
            query (QueryType): Choice of query type to perform a
                check of the number of rows that match the clause.

        Raises:
            :class:`~ape.exceptions.QueryEngineError`: When given an
                incompatible QueryType.

        Returns:
            `sqlalchemy.sql.expression.Select`
        """

        raise QueryEngineError(
            """
            Not a compatible QueryType. For more details see our docs
            https://docs.apeworx.io/ape/stable/methoddocs/exceptions.html#ape.exceptions.QueryEngineError
            """
        )

    @_estimate_query_clause.register
    def _block_estimate_query_clause(self, query: BlockQuery) -> Select:
        return (
            select(func.count())
            .select_from(Blocks)
            .where(Blocks.number >= query.start_block)
            .where(Blocks.number <= query.stop_block)
            .where(Blocks.number % query.step == 0)
        )

    @_estimate_query_clause.register
    def _transaction_estimate_query_clause(self, query: BlockTransactionQuery) -> Select:
        return (
            select(func.count())
            .select_from(Transactions)
            .where(Transactions.block_hash == query.block_id)
        )

    @_estimate_query_clause.register
    def _contract_events_estimate_query_clause(self, query: ContractEventQuery) -> Select:
        return (
            select(func.count())
            .select_from(ContractEvents)
            .where(ContractEvents.block_number >= query.start_block)
            .where(ContractEvents.block_number <= query.stop_block)
            .where(ContractEvents.block_number % query.step == 0)
        )

    @singledispatchmethod
    def _compute_estimate(self, query: QueryType, result: CursorResult) -> Optional[int]:
        """
        A singledispatchemethod that computes the time a query
        will take to perform from the caching database
        """

        return None  # can't handle this query

    @_compute_estimate.register
    def _compute_estimate_block_query(
        self,
        query: BlockQuery,
        result: CursorResult,
    ) -> Optional[int]:
        if result.scalar() == (1 + query.stop_block - query.start_block) // query.step:
            # NOTE: Assume 200 msec to get data from database
            return 200

        # Can't handle this query
        # TODO: Allow partial queries
        return None

    @_compute_estimate.register
    def _compute_estimate_block_transaction_query(
        self,
        query: BlockTransactionQuery,
        result: CursorResult,
    ) -> Optional[int]:
        # TODO: Update `transactions` table schema so this query functions properly
        # Uncomment below after https://github.com/ApeWorX/ape/issues/994
        # if result.scalar() > 0:  # type: ignore
        #    # NOTE: Assume 200 msec to get data from database
        #    return 200

        # Can't handle this query
        return None

    @_compute_estimate.register
    def _compute_estimate_contract_events_query(
        self,
        query: ContractEventQuery,
        result: CursorResult,
    ) -> Optional[int]:
        if result.scalar() == (query.stop_block - query.start_block) // query.step:
            # NOTE: Assume 200 msec to get data from database
            return 200

        # Can't handle this query
        # TODO: Allow partial queries
        return None

    def estimate_query(self, query: QueryType) -> Optional[int]:
        """
        Method called by the client to return a query time estimate.

        Args:
            query (QueryType): Choice of query type to perform a
                check of the number of rows that match the clause.

        Returns:
            Optional[int]
        """

        # NOTE: Because of Python shortcircuiting, the first time `database_connection` is missing
        #       this will lock the class var `database_bypass` in place for the rest of the session
        if self.database_bypass or self.database_connection is None:
            # No database, or some other issue
            return None

        try:
            with self.database_connection as conn:
                result = conn.execute(self._estimate_query_clause(query))
                if not result:
                    return None

                return self._compute_estimate(query, result)

        except QueryEngineError as err:
            logger.debug(f"Bypassing cache database: {err}")
            # Note: The reason we return None instead of failing is that we want
            #       a failure of the query to bypass the query logic so that the
            #       estimation phase does not fail in `QueryManager`.
            return None

    @singledispatchmethod
    def perform_query(self, query: QueryType) -> Iterator:  # type: ignore
        """
        Performs the requested query from cache.

        Args:
            query (QueryType): Choice of query type to perform a
                check of the number of rows that match the clause.

        Raises:
            :class:`~ape.exceptions.QueryEngineError`: When given an
                incompatible QueryType, or encounters some sort of error
                in the database or estimation logic.

        Returns:
            Iterator
        """

        raise QueryEngineError(
            "Not a compatible QueryType. For more details see our docs "
            "https://docs.apeworx.io/ape/stable/methoddocs/"
            "exceptions.html#ape.exceptions.QueryEngineError"
        )

    @perform_query.register
    def _perform_block_query(self, query: BlockQuery) -> Iterator[BlockAPI]:
        with self.database_connection as conn:
            result = conn.execute(
                select([column(c) for c in query.columns])
                .where(Blocks.number >= query.start_block)
                .where(Blocks.number <= query.stop_block)
                .where(Blocks.number % query.step == 0)
            )

            if not result:
                # NOTE: Should be unreachable if estimated correctly
                raise QueryEngineError(f"Could not perform query:\n{query}")

            yield from map(
                lambda row: self.provider.network.ecosystem.decode_block(dict(row.items())), result
            )

    @perform_query.register
    def _perform_transaction_query(self, query: BlockTransactionQuery) -> Iterator[dict]:
        with self.database_connection as conn:
            result = conn.execute(
                select([Transactions]).where(Transactions.block_hash == query.block_id)
            )

            if not result:
                # NOTE: Should be unreachable if estimated correctly
                raise QueryEngineError(f"Could not perform query:\n{query}")

            yield from map(lambda row: dict(row.items()), result)

    @perform_query.register
    def _perform_contract_events_query(self, query: ContractEventQuery) -> Iterator[ContractLog]:
        with self.database_connection as conn:
            result = conn.execute(
                select([column(c) for c in query.columns])
                .where(ContractEvents.block_number >= query.start_block)
                .where(ContractEvents.block_number <= query.stop_block)
                .where(ContractEvents.block_number % query.step == 0)
            )

            if not result:
                # NOTE: Should be unreachable if estimated correctly
                raise QueryEngineError(f"Could not perform query:\n{query}")

            yield from map(lambda row: ContractLog.model_validate(dict(row.items())), result)

    @singledispatchmethod
    def _cache_update_clause(self, query: QueryType) -> Insert:
        """
        Update cache database Insert statement.

        Args:
            query (QueryType): Choice of query type to perform a
                check of the number of rows that match the clause.

        Raises:
            :class:`~ape.exceptions.QueryEngineError`: When given an
                incompatible QueryType, or encounters some sort of error
                in the database or estimation logic.

        Returns:
            `sqlalchemy.sql.Expression.Insert`
        """
        # Can't cache this query
        raise QueryEngineError(
            "Not a compatible QueryType. For more details see our docs "
            "https://docs.apeworx.io/ape/stable/methoddocs/"
            "exceptions.html#ape.exceptions.QueryEngineError"
        )

    @_cache_update_clause.register
    def _cache_update_block_clause(self, query: BlockQuery) -> Insert:
        return insert(Blocks)

    # TODO: Update `transactions` table schema so we can use `EcosystemAPI.decode_receipt`
    # Uncomment below after https://github.com/ApeWorX/ape/issues/994
    # @_cache_update_clause.register
    # def _cache_update_block_txns_clause(self, query: BlockTransactionQuery) -> Insert:
    #    return insert(Transactions)  # type: ignore

    @_cache_update_clause.register
    def _cache_update_events_clause(self, query: ContractEventQuery) -> Insert:
        return insert(ContractEvents)

    @singledispatchmethod
    def _get_cache_data(
        self, query: QueryType, result: Iterator[BaseInterfaceModel]
    ) -> Optional[list[dict[str, Any]]]:
        raise QueryEngineError(
            """
            Not a compatible QueryType. For more details see our docs
            https://docs.apeworx.io/ape/stable/methoddocs/exceptions.html#ape.exceptions.QueryEngineError
            """
        )

    @_get_cache_data.register
    def _get_block_cache_data(
        self, query: BlockQuery, result: Iterator[BaseInterfaceModel]
    ) -> Optional[list[dict[str, Any]]]:
        return [m.model_dump(mode="json", by_alias=False) for m in result]

    @_get_cache_data.register
    def _get_block_txns_data(
        self, query: BlockTransactionQuery, result: Iterator[BaseInterfaceModel]
    ) -> Optional[list[dict[str, Any]]]:
        new_result = []
        table_columns = [c.key for c in Transactions.__table__.columns]  # type: ignore
        txns: list[TransactionAPI] = cast(list[TransactionAPI], result)
        for val in [m for m in txns]:
            new_dict = {
                k: v
                for k, v in val.model_dump(mode="json", by_alias=False).items()
                if k in table_columns
            }
            for col in table_columns:
                if col == "txn_hash":
                    new_dict["txn_hash"] = val.txn_hash
                elif col == "sender":
                    new_dict["sender"] = new_dict["sender"].encode()
                elif col == "receiver" and "receiver" in new_dict:
                    new_dict["receiver"] = new_dict["receiver"].encode()
                elif col == "receiver" and "receiver" not in new_dict:
                    new_dict["receiver"] = b""
                elif col == "block_hash":
                    new_dict["block_hash"] = query.block_id
                elif col == "signature" and val.signature is not None:
                    new_dict["signature"] = val.signature.encode_rsv()
                elif col not in new_dict:
                    new_dict[col] = None
            new_result.append(new_dict)
        return new_result

    @_get_cache_data.register
    def _get_cache_events_data(
        self, query: ContractEventQuery, result: Iterator[BaseInterfaceModel]
    ) -> Optional[list[dict[str, Any]]]:
        return [m.model_dump(mode="json", by_alias=False) for m in result]

    def update_cache(self, query: QueryType, result: Iterator[BaseInterfaceModel]):
        try:
            clause = self._cache_update_clause(query)
        except QueryEngineError:
            # Cannot handle query type
            return

        # NOTE: Because of Python shortcircuiting, the first time `database_connection` is missing
        #       this will lock the class var `database_bypass` in place for the rest of the session
        if not self.database_bypass and self.database_connection is not None:
            logger.debug(f"Caching query: {query}")
            with self.database_connection as conn:
                try:
                    conn.execute(
                        clause.values(  # type: ignore
                            self._get_cache_data(query, result)
                        ).prefix_with("OR IGNORE")
                    )

                except QueryEngineError as err:
                    logger.warning(f"Database corruption: {err}")
