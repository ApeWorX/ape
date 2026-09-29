from abc import abstractmethod
from collections.abc import Iterator, Sequence
from functools import cache, cached_property
from importlib.util import find_spec
from typing import TYPE_CHECKING, Any, ClassVar, Generic, TypeAlias, TypeVar

import narwhals as nw
from ethpm_types.abi import EventABI, MethodABI
from pydantic import NonNegativeInt, PositiveInt, field_validator, model_validator

from ape.exceptions import QueryEngineError
from ape.logging import logger
from ape.types import ContractLog
from ape.types.address import AddressType
from ape.utils.basemodel import BaseInterface, BaseInterfaceModel, BaseModel, ManagerAccessMixin

from .providers import BlockAPI
from .transactions import ReceiptAPI, TransactionAPI

if TYPE_CHECKING:
    from narwhals.typing import Frame

    from ape.managers.query import QueryResult

    try:
        # Only on Python 3.11
        from typing import Self  # type: ignore
    except ImportError:
        from typing_extensions import Self  # type: ignore


_DATAFRAME_BACKEND_HELP = (
    "Install a Narwhals-supported dataframe library (for example `polars` or `pandas`), "
    "or pass `backend=`."
)

# `from_dict` only accepts eager backends. Polars is preferred when several are installed.
_EAGER_DATAFRAME_BACKENDS: tuple[tuple[str, str], ...] = (
    ("polars", "polars"),
    ("pandas", "pandas"),
    ("pyarrow", "pyarrow"),
    ("modin", "modin.pandas"),
    ("cudf", "cudf"),
)


@cache
def _detected_dataframe_backend() -> nw.Implementation | None:
    """Return the first installed eager dataframe library, without importing it."""
    for name, module in _EAGER_DATAFRAME_BACKENDS:
        if find_spec(module) is not None:
            return nw.Implementation.from_backend(name)

    return None


def resolve_dataframe_backend(
    backend: str | nw.Implementation | None,
    configured: str | nw.Implementation | None,
) -> nw.Implementation:
    """Select the dataframe library `.query` will use to build a Narwhals frame.

    An explicit `backend` wins, then `query.backend` when it is set. Otherwise
    Ape uses an installed library, preferring Polars. The choice is cached for
    the process. Protocol SDKs use the Narwhals API and do not pin a library.
    """
    chosen = configured if backend is None else backend
    if chosen is None:
        chosen = _detected_dataframe_backend()

    if chosen is None:
        raise QueryEngineError(
            "`.query` returns a Narwhals DataFrame and needs a dataframe library. "
            f"{_DATAFRAME_BACKEND_HELP}"
        )

    if not isinstance(chosen, nw.Implementation):
        chosen = nw.Implementation.from_backend(chosen)

    if chosen is nw.Implementation.UNKNOWN:
        raise QueryEngineError(
            f"{backend!r} is not a Narwhals dataframe backend. {_DATAFRAME_BACKEND_HELP}"
        )

    try:
        # Import happens here so a missing library fails before any query work,
        # and so the rest of Ape never imports a dataframe package.
        chosen.to_native_namespace()
    except ModuleNotFoundError as err:
        raise QueryEngineError(
            f"`.query` is set to use the {chosen.value!r} dataframe backend, "
            "but that library is not installed. "
            f"{_DATAFRAME_BACKEND_HELP}"
        ) from err

    return chosen


def to_dataframe(
    data: dict[str, list],
    backend: str | nw.Implementation | None,
    configured: str | nw.Implementation | None,
) -> nw.DataFrame:
    """Build the Narwhals DataFrame returned by `.query`."""
    resolved = resolve_dataframe_backend(backend, configured)
    return nw.from_dict(data, backend=resolved)


def _subclass_tree(model: type[BaseInterfaceModel]) -> list[type[BaseInterfaceModel]]:
    found: list[type[BaseInterfaceModel]] = []
    stack: list[type] = list(model.__subclasses__())
    while stack:
        cls = stack.pop()
        if cls in found or not issubclass(cls, BaseInterfaceModel):
            continue

        found.append(cls)
        stack.extend(cls.__subclasses__())

    return found


def _ecosystem_packages() -> set[str] | None:
    """Packages that define the connected ecosystem's models.

    The ecosystem class and the classes it extends are included, stopping at
    ``EcosystemAPI``. A chain that subclasses Ethereum and declares no model of
    its own still uses the Ethereum block and receipt.
    """
    networks = ManagerAccessMixin.network_manager
    if not networks.connected:
        return None

    packages: set[str] = set()
    for cls in type(networks.ecosystem).__mro__:
        if cls.__name__ == "EcosystemAPI":
            break

        packages.add(cls.__module__.split(".", 1)[0])

    return packages


def _concrete_model(model: type[BaseInterfaceModel]) -> type[BaseInterfaceModel]:
    """The connected ecosystem's model for ``model``.

    The most general class in that ecosystem's packages is the one every row
    has. A more specific variant, such as a blob receipt, is not used for ``*``.
    """
    packages = _ecosystem_packages()
    if not packages:
        return model

    candidates = [
        cls for cls in _subclass_tree(model) if cls.__module__.split(".", 1)[0] in packages
    ]
    general = [
        cls
        for cls in candidates
        if not any(cls is not other and issubclass(cls, other) for other in candidates)
    ]
    if len(general) == 1:
        return general[0]

    return model


def _basic_columns(model: type[BaseInterfaceModel]) -> set[str]:
    # Constructor fields of the ecosystem model. Enough to build a row, and not
    # properties that fetch more data.
    return set(_concrete_model(model).model_fields)


def _all_columns(model: type[BaseInterfaceModel]) -> set[str]:
    concrete = _concrete_model(model)
    columns = set(concrete.model_fields)
    for cls in concrete.__mro__:
        if cls is BaseInterfaceModel or not issubclass(cls, BaseInterfaceModel):
            continue

        columns.update(
            field_name
            for field_name, field in vars(cls).items()
            if not field_name.startswith("_") and isinstance(field, (property, cached_property))
        )

    # Receipt rows expose the nested transaction's fields, such as nonce.
    if issubclass(concrete, ReceiptAPI):
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

        # Keep the caller's order. Drop names this model does not have.
        selected_fields = [column for column in columns if column in all_columns]
        if len(selected_fields) > 0:
            return list(dict.fromkeys(selected_fields))

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
    Model: ClassVar[type[BaseInterfaceModel] | None] = None

    columns: list[str]

    @field_validator("columns", mode="before")
    def expand_wildcard(cls, value: Any) -> Any:
        if cls.Model:
            return validate_and_expand_columns(value, cls.Model)

        return value

    # Methods for determining query "coverage" and constraining search
    @property
    def start_index(self) -> int:
        raise NotImplementedError()

    @property
    def end_index(self) -> int:
        raise NotImplementedError()

    def __len__(self) -> int:
        # Ranges are inclusive. An empty span (such as a block with no transactions)
        # has ``end_index < start_index`` and length 0.
        if self.end_index < self.start_index:
            return 0

        step = getattr(self, "step", 1) or 1
        return (self.end_index - self.start_index) // step + 1

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


class BlockQuery(_BaseBlockQuery, _BaseQuery[BlockAPI]):
    """
    A ``QueryType`` that collects properties of ``BlockAPI`` over a range of
    blocks between ``start_block`` and ``stop_block``.
    """


class BlockTransactionQuery(_BaseQuery[TransactionAPI]):
    """
    A ``QueryType`` that collects properties of ``TransactionAPI`` over a range of
    transactions collected inside the ``BlockAPI` object represented by ``block_id``.
    """

    Model = TransactionAPI

    block_id: Any
    num_transactions: NonNegativeInt

    @property
    def start_index(self) -> int:
        return 0

    @property
    def end_index(self) -> int:
        return self.num_transactions - 1


class AccountTransactionQuery(_BaseQuery[ReceiptAPI]):
    """
    A ``QueryType`` that collects properties of ``ReceiptAPI`` over a range
    of transactions made by ``account`` between ``start_nonce`` and ``stop_nonce``.
    """

    Model = ReceiptAPI

    account: AddressType
    start_nonce: NonNegativeInt = 0
    stop_nonce: NonNegativeInt

    @model_validator(mode="before")
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


class ContractCreation(BaseInterfaceModel):
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

    factory: AddressType | None = None
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


class ContractCreationQuery(_BaseQuery[ContractCreation]):
    """
    A ``QueryType`` that obtains information about contract deployment.
    Returns ``ContractCreation(txn_hash, block, deployer, factory)``.
    """

    Model = ContractCreation

    contract: AddressType

    @property
    def start_index(self) -> int:
        return 0

    @property
    def end_index(self) -> int:
        # One creation record occupies a single index.
        return 0


class ContractEventQuery(_BaseBlockQuery, _BaseQuery[ContractLog]):
    """
    A ``QueryType`` that collects members from ``event`` over a range of
    logs emitted by ``contract`` between ``start_block`` and ``stop_block``.
    """

    Model = ContractLog

    contract: list[AddressType] | AddressType
    event: EventABI
    search_topics: dict[str, Any] | None = None


class ContractMethodQuery(_BaseBlockQuery, _BaseQuery[Any]):
    """
    A ``QueryType`` that collects return values from calling ``method`` in ``contract``
    over a range of blocks between ``start_block`` and ``stop_block``.
    """

    # Return columns are method outputs, not block fields.
    Model = None

    contract: AddressType
    method: MethodABI
    method_args: dict[str, Any]


class CursorAPI(BaseInterfaceModel, Generic[ModelType]):
    query: _BaseQuery[ModelType]

    def shrink(
        self,
        start_index: int | None = None,
        end_index: int | None = None,
    ) -> "Self":
        """
        Create a copy of this object with the query window shrunk inwards to `start_index` and/or
        `end_index`. Note that `.shrink` should always be called with strictly less coverage than
        original query window of this cursor model for use in the `QueryManager`'s solver algorithm.

        Args:
            start_index (int | None): The new `start_index` that this cursor should start at.
            end_index (int | None): The new `end_index` that this cursor should start at.

        Returns:
            Self: a copy of itself, only with the smaller query window applied.
        """
        raise NotImplementedError

    @property
    def total_time(self) -> float:
        """
        The estimated total time that this cursor would take to execute. Note that this is only an
        approximation, but should be relatively accurate for the `QueryManager`'s solver algorithm
        to work well. Is used for printing metrics to the user.

        Default implementation of this property is the span of this cursor times `.time_per_row`.

        Returns:
            float: Time (in seconds) that the query should take to execute fully.
        """
        return len(self.query) * self.time_per_row

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
    def as_dataframe(self, backend: nw.Implementation) -> "Frame":
        """
        Execute and return this Cursor as a `~narwhals.v1.DataFrame` or `~narwhals.v1.LazyFrame`
        object. The use of `backend is exactly as it is mentioned in the `narwhals` documentation:
        https://narwhals-dev.github.io/narwhals/api-reference/typing/#narwhals.typing.Frame

        It is recommended to use whatever method of conversion makes sense within your query
        plugin, for example you can use `~narwhals.from_dict` to convert results into a Frame:
        https://narwhals-dev.github.io/narwhals/api-reference/narwhals/#narwhals.from_dict

        Default implementation of this method uses `.as_model_iter()` to fulfill this requirement.

        Args:
            backend (:object:`~narwhals.Implementation): A Narwhals-compatible backend specifier.
                See: https://narwhals-dev.github.io/narwhals/api-reference/implementation/

        Returns:
            (`~narwhals.v1.DataFrame` | `~narwhals.v1.LazyFrame`): A narwhals dataframe.
        """
        data: dict[str, list] = {column: [] for column in self.query.columns}

        for item in self.as_model_iter():
            for column in data:
                data[column].append(getattr(item, column))

        return nw.from_dict(data, backend=backend)

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


QueryType: TypeAlias = (
    AccountTransactionQuery
    | BlockQuery
    | BlockTransactionQuery
    | ContractCreationQuery
    | ContractEventQuery
    | ContractMethodQuery
)


class QueryEngineAPI(BaseInterface):
    def execute(self, query: QueryType) -> Iterator[CursorAPI]:
        """
        Obtain `CursorAPI` object(s) that may covers (subset of) `query`. A plugin should yield
        one or more cursor(s) that covers some subset of the length of `query`'s row-space, as
        indicated by `QueryType.start_index` and `QueryType.end_index`. These query types will
        either be fed into an algorithm to determine the cheapest possible coverage of the query,
        or be sourced directly from the provider in response to a user-specified query.

        Note that this method encourages the use of `@singledispatchmethod` decorator to make it
        possible to specify only certain types of queries that your plugin might be able to handle,
        which will cause it to skip using this plugin for non-overriden queries by default, as this
        method yields an empty iterator which will indicate that your plugin can be skipped.

        Add `execute = functools.singledispatchmethod(QueryEngineAPI.execute)` to your subclass,
        and then `@execute.register` as a decorator on your method in order to support particular
        query types.

        Args:
            query (`~QueryType`): The query being handled by this method.

        Returns:
            Iterator[`~CursorAPI`]: Zero (or more) cursor(s) that provide data for a portion of
                `query`'s range. Defaults to not providing any coverage.

        Usage example::

            >>> from functools import singledispatchmethod
            >>> from ape.api import CursorAPI, QueryEngineAPI
            >>> class PluginCursor(CursorAPI):
            ...     ...  # See `CursorAPI`'s documentation for methods to implement
            >>> class PluginQueryEngine(QueryEngineAPI):
            ...     # NOTE: Do this if you want to define multiple dispatch handlers easily
            ...     execute = singledispatchmethod(QueryEngineAPI.execute)
            ...     # NOTE: Do *not* use the name `execute` for the dispatch method's name!
            ...     @execute.register
            ...     def exec_queryX(self, query: SomethingQuery) -> Iterator[PluginCursor]:
            ...         yield PluginCursor(query=query, ...)
            ...         # NOTE: Can yield more cursors if plugin does not have full coverage,
            ...         #       or has piece-wise coverage of the query space

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


# TODO: Remove in v1. Plugins should import ``QueryEngineAPI``.
QueryAPI = QueryEngineAPI
