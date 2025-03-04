from abc import abstractmethod
from collections.abc import Iterator, Sequence
from functools import cache, cached_property
from typing import TYPE_CHECKING, Any, ClassVar, Generic, Optional, TypeVar, Union

from ethpm_types.abi import EventABI, MethodABI
from pydantic import NonNegativeInt, PositiveInt, field_validator, model_validator

from ape.logging import logger
from ape.types.address import AddressType
from ape.utils import singledispatchmethod
from ape.utils.basemodel import BaseInterface, BaseInterfaceModel, BaseModel

from .providers import BlockAPI
from .transactions import ReceiptAPI, TransactionAPI

if TYPE_CHECKING:
    from narwhals.typing import Frame
    from narwhals.typing import Implementation as DataframeImplementation

    from ape.managers.query import QueryResult

    try:
        # Only on Python 3.11
        from typing import Self  # type: ignore
    except ImportError:
        from typing_extensions import Self  # type: ignore


@cache
def _basic_columns(Model: type[BaseInterfaceModel]) -> set[str]:
    columns = set(Model.__pydantic_fields__)

    # TODO: Remove once `ReceiptAPI` fields cleaned up for better processing
    if Model == ReceiptAPI:
        columns.remove("transaction")
        columns |= _basic_columns(TransactionAPI)

    return columns


@cache
def _all_columns(Model: type[BaseInterfaceModel]) -> set[str]:
    columns = _basic_columns(Model)
    # NOTE: Iterate down the series of subclasses of `Model` (e.g. Block and BlockAPI)
    #       and get all of the public property methods of each class (which are valid columns)
    columns |= {
        field_name
        for cls in Model.__mro__
        if issubclass(cls, BaseInterfaceModel) and cls is not BaseInterfaceModel
        for field_name, field in vars(cls).items()
        if not field_name.startswith("_") and isinstance(field, (property, cached_property))
    }

    # TODO: Remove once `ReceiptAPI` fields cleaned up for better processing
    if Model == ReceiptAPI:
        columns |= _all_columns(TransactionAPI)

    return columns


def validate_and_expand_columns(
    columns: Sequence[str], Model: type[BaseInterfaceModel]
) -> list[str]:
    if len(columns) == 1 and columns[0] == "*":
        # NOTE: By default, only pull explicit fields
        #       (because they are cheap to pull, but properties might not be)
        return sorted(_basic_columns(Model))

    else:
        # NOTE: Validate if selected columns in the total set of fields + properties
        all_columns = _all_columns(Model)
        deduped_columns = set(columns)
        if len(deduped_columns) != len(columns):
            logger.warning(f"Duplicate fields in {columns}")

        # NOTE: Some unrecognized fields, but can still provide the rest of the data
        if len(deduped_columns - all_columns) > 0:
            err_msg = _unrecognized_columns(deduped_columns, all_columns)
            logger.warning(err_msg)

        # NOTE: Only select recognized fields and return them (in sorted order)
        selected_fields = all_columns.intersection(deduped_columns)
        if len(selected_fields) > 0:
            return sorted(selected_fields)

    # NOTE: No recognized fields available to query, so raise ValueError
    err_msg = _unrecognized_columns(deduped_columns, all_columns)
    raise ValueError(err_msg)


def _unrecognized_columns(selected_columns: set[str], all_columns: set[str]) -> str:
    unrecognized = "', '".join(sorted(selected_columns - all_columns))
    all_cols = ", ".join(sorted(all_columns))
    return f"Unrecognized field(s) '{unrecognized}', must be one of '{all_cols}'."


def extract_fields(item: BaseInterfaceModel, columns: Sequence[str]) -> list[Any]:
    return [getattr(item, col, None) for col in columns]


ModelType = TypeVar("ModelType", bound=BaseInterfaceModel)


class _BaseQuery(BaseModel, Generic[ModelType]):
    Model: ClassVar[ModelType]
    columns: set[str]

    @field_validator("columns", mode="before")
    def expand_wildcard(cls, value: Any) -> Any:
        if isinstance(value, str) and value == "*":
            return _basic_columns(cls.Model)

        return value

    # Methods for determining query "coverage" and constraining search
    @property
    def start_index(self) -> int:
        raise NotImplementedError()

    @property
    def end_index(self) -> int:
        raise NotImplementedError()

    def __len__(self) -> int:
        return self.end_index - self.start_index

    def __contains__(self, other: Any) -> bool:
        if not isinstance(other, _BaseQuery):
            raise ValueError()

        # NOTE: Return True if `other` is "covered by" `self`
        return other.start_index >= self.start_index and other.end_index <= self.end_index

    # Methods for determining query "ordering"
    def __lt__(self, other: Any) -> bool:
        if not isinstance(other, _BaseQuery):
            raise ValueError()

        if self.start_index < other.start_index:
            return True

        elif self.start_index == other.start_index:
            # NOTE: If start matches, return True for smaller range covered
            return self.end_index < other.end_index

        else:
            return False


class _BaseBlockQuery(_BaseQuery):
    Model = BlockAPI
    start_block: NonNegativeInt = 0
    stop_block: NonNegativeInt
    step: PositiveInt = 1

    @model_validator(mode="before")
    @classmethod
    def check_start_block_before_stop_block(cls, values):
        start_block = values.get("start_block")
        stop_block = values.get("stop_block")
        if (
            isinstance(start_block, int)
            and isinstance(stop_block, int)
            and stop_block < start_block
        ):
            raise ValueError(
                f"stop_block: '{values['stop_block']}' cannot be less than "
                f"start_block: '{values['start_block']}'."
            )

        return values

    @property
    def start_index(self) -> int:
        return self.start_block

    @property
    def end_index(self) -> int:
        return self.stop_block


class BlockQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects properties of ``BlockAPI`` over a range of
    blocks between ``start_block`` and ``stop_block``.
    """


class BlockTransactionQuery(_BaseQuery):
    """
    A ``QueryType`` that collects properties of ``TransactionAPI`` over a range of
    transactions collected inside the ``BlockAPI` object represented by ``block_id``.
    """

    block_id: Any
    num_transactions: NonNegativeInt

    @property
    def start_index(self) -> int:
        return 0

    @property
    def end_index(self) -> int:
        return self.num_transactions - 1


class AccountTransactionQuery(_BaseQuery):
    """
    A ``QueryType`` that collects properties of ``TransactionAPI`` over a range
    of transactions made by ``account`` between ``start_nonce`` and ``stop_nonce``.
    """

    account: AddressType
    start_nonce: NonNegativeInt = 0
    stop_nonce: NonNegativeInt

    @model_validator(mode="before")
    @classmethod
    def check_start_nonce_before_stop_nonce(cls, values: dict) -> dict:
        if values["stop_nonce"] < values["start_nonce"]:
            raise ValueError(
                f"stop_nonce: '{values['stop_nonce']}' cannot be less than "
                f"start_nonce: '{values['start_nonce']}'."
            )

        return values

    @property
    def start_index(self) -> int:
        return self.start_nonce

    @property
    def end_index(self) -> int:
        return self.stop_nonce


class ContractCreationQuery(_BaseQuery):
    """
    A ``QueryType`` that obtains information about contract deployment.
    Returns ``ContractCreation(txn_hash, block, deployer, factory)``.
    """

    contract: AddressType


class ContractCreation(BaseModel, BaseInterface):
    """
    Contract-creation metadata, such as the transaction
    and deployer. Useful for contract-verification,
    ``block_identifier=`` usage, and other use-cases.

    To get contract-creation metadata, you need a query engine
    that can provide it, such as the ``ape-etherscan`` plugin
    or a node connected to the OTS namespace.
    """

    txn_hash: str
    """
    The transaction hash of the deploy transaction.
    """

    block: int
    """
    The block number of the deploy transaction.
    """

    deployer: AddressType
    """
    The contract deployer address.
    """

    factory: Optional[AddressType] = None
    """
    The address of the factory contract, if there is one
    and it is known (depends on the query provider!).
    """

    @property
    def receipt(self) -> ReceiptAPI:
        """
        The deploy transaction :class:`~ape.api.transactions.ReceiptAPI`.
        """
        return self.chain_manager.get_receipt(self.txn_hash)

    @classmethod
    def from_receipt(cls, receipt: ReceiptAPI) -> "ContractCreation":
        """
        Create a metadata class.

        Args:
            receipt (:class:`~ape.api.transactions.ReceiptAPI`): The receipt
              of the deploy transaction.

        Returns:
            :class:`~ape.api.query.ContractCreation`
        """
        return cls(
            txn_hash=receipt.txn_hash,
            block=receipt.block_number,
            deployer=receipt.sender,
            # factory is not detected since this is meant for eoa deployments
        )


class ContractEventQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects members from ``event`` over a range of
    logs emitted by ``contract`` between ``start_block`` and ``stop_block``.
    """

    contract: Union[list[AddressType], AddressType]
    event: EventABI
    search_topics: Optional[dict[str, Any]] = None


class ContractMethodQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects return values from calling ``method`` in ``contract``
    over a range of blocks between ``start_block`` and ``stop_block``.
    """

    contract: AddressType
    method: MethodABI
    method_args: dict[str, Any]


QueryType = TypeVar("QueryType", bound=_BaseQuery)


class BaseCursorAPI(BaseInterfaceModel, Generic[QueryType, ModelType]):
    query: QueryType

    @abstractmethod
    def shrink(
        self,
        start_index: Optional[int] = None,
        end_index: Optional[int] = None,
    ) -> "Self":
        """
        Create a copy of this object with the query window shrunk inwards to `start_index` and/or
        `end_index`. Note that `.shrink` should always be called with strictly less coverage than
        original query window of this cursor model for use in the `QueryManager`'s solver algorithm.

        Args:
            start_index (Optional[int]): The new `start_index` that this cursor should start at.
            end_index (Optional[int]): The new `end_index` that this cursor should start at.

        Returns:
            Self: a copy of itself, only with the smaller query window applied.
        """

    @property
    @abstractmethod
    def total_time(self) -> float:
        """
        The estimated total time that this cursor would take to execute. Note that this is only an
        approximation, but should be relatively accurate for the `QueryManager`'s solver algorithm
        to work well. Is used for printing metrics to the user.

        Returns:
            float: Time (in seconds) that the query should take to execute fully.
        """

    @property
    @abstractmethod
    def time_per_row(self) -> float:
        """
        The estimated average time spent (per row) that this cursor would take to execute. Note
        that this is only an approximation, but should be relatively accurate for the
        `QueryManager`'s solver algorithm to work well. Is used for determining the correct
        ordering of cursor's within the solver algorithm.

        Returns:
            float: Average time (in seconds) that the query should take to execute a single row.
        """

    # Conversion out to fulfill user query requirements
    @abstractmethod
    def as_dataframe(self, backend: "DataframeImplementation") -> "Frame":
        """
        Execute and return this Cursor as a `~narwhals.v1.DataFrame` or `~narwhals.v1.LazyFrame`
        object. The use of `backend is exactly as it is mentioned in the `narwhals` documentation:
        https://narwhals-dev.github.io/narwhals/api-reference/typing/#narwhals.typing.Frame

        It is recommended to use whatever method of conversion makes sense within your query
        plugin, for example you can use `~narwhals.from_dict` to convert results into a Frame:
        https://narwhals-dev.github.io/narwhals/api-reference/narwhals/#narwhals.from_dict

        Args:
            backend (:object:`~narwhals.Implementation): A Narwhals-compatible backend specifier.
                See: https://narwhals-dev.github.io/narwhals/api-reference/implementation/

        Returns:
            (`~narwhals.v1.DataFrame` | `~narwhals.v1.LazyFrame`): A narwhals dataframe.
        """

    @abstractmethod
    def as_model_iter(self) -> Iterator[ModelType]:
        """
        Execute and return this Cursor as an iterated sequence of `ModelType` objects. This will
        be used for Ape's internal APIs in order to fulfill certain higher-level use cases within
        Ape. Note that a plugin is expected to assemble this iterated sequence in the most
        efficient manner possible.

        Returns:
            `Iterator[ModelType]`: A sequence of Ape API models.
        """


class QueryEngineAPI(BaseInterface):
    @singledispatchmethod
    def exec(self, query: QueryType) -> Iterator[BaseCursorAPI]:
        """
        Obtain `BaseCursorAPI` object(s) that may covers (subset of) `query`. A plugin should yield
        one or more cursor(s) that covers some subset of the length of `query`'s row-space, as
        indicated by `QueryType.start_index` and `QueryType.end_index`. These query types will
        either be fed into an algorithm to determine the cheapest possible coverage of the query,
        or be sourced directly from the provider in response to a user-specified query.

        Note that this method uses `@singledispatchmethod` decorator to make it possible to specify
        only certain types of queries that your plugin might be able to handle, which will cause it
        to skip using this plugin for non-overriden queries by default, as this method yields an
        empty iterator which will indicate that your plugin can be skipped.

        Add `@QueryEngineAPI.exec.register` as a decorator on your method in order to add support
        for particular query types.

        Args:
            query (`~QueryType`): The query being handled by this method.

        Returns:
            Iterator[`~BaseCursorAPI`]: Zero (or more) cursor(s) that provide data for a portion of
                `query`'s range. Defaults to not providing any coverage.

        Usage example::

            >>> from ape.api import QueryEngineAPI
            >>> class PluginQueryEngine(QueryEngineAPI):
            ...     @QueryEngineAPI.exec.register
            ...     def exec_queryX(self, query: SomethingQuery) -> Iterator[PluginCursorSubclass]:
            ...         yield PluginCursorSubclass(query=query, ...)
            ...         # NOTE: Can yield more if plugin does not have full coverage of query
        """
        return iter([])  # Will avoid using any cursors from this plugin for querying this type

    def cache(self, result: "QueryResult"):
        """
        Once a query is solved, this method will be called on every query plugin as a callback for
        whatever application logic you might want to perform using the final `QueryResult` cursor.
        By default, this method does nothing, so only override if it is needed to perform specific
        application logic for your plugin (caching, pre-indexing, etc.)

        Args:
            result (`~ape.managers.query.QueryResult`): the final solved Cursor representing all
                the data that most efficiently covers the original `~QueryType`.
        """

    # TODO: Deprecate below in v0.9
    @abstractmethod
    def estimate_query(self, query: QueryType) -> Optional[int]:
        """
        Estimation of time needed to complete the query. The estimation is returned
        as an int representing milliseconds. A value of None indicates that the
        query engine is not available for use or is unable to complete the query.

        Args:
            query (``QueryType``): Query to estimate.

        Returns:
            Optional[int]: Represents milliseconds, returns ``None`` if unable to execute.

        """

    @abstractmethod
    def perform_query(self, query: QueryType) -> Iterator:
        """
        Executes the query using best performing ``estimate_query`` query engine.

        Args:
            query (``QueryType``): query to execute

        Returns:
            Iterator
        """

    def update_cache(self, query: QueryType, result: Iterator[BaseInterfaceModel]):
        """
        Allows a query plugin the chance to update any cache using the results obtained
        from other query plugins. Defaults to doing nothing, override to store cache data.

        Args:
            query (``QueryType``): query that was executed
            result (``Iterator``): the result of the query
        """


# TODO: Remove in v0.9
QueryAPI = QueryEngineAPI
