from functools import lru_cache
from typing import Any, Dict, Iterator, List, Optional, Sequence, Set, Type, Union

from ethpm_types.abi import BaseModel, EventABI, MethodABI
from pydantic import NonNegativeInt, PositiveInt, model_validator

from ape.api.transactions import ReceiptAPI, TransactionAPI
from ape.logging import logger
from ape.types import AddressType
from ape.utils import BaseInterface, BaseInterfaceModel, abstractmethod, cached_property

QueryType = Union[
    "BlockQuery",
    "BlockTransactionQuery",
    "AccountTransactionQuery",
    "ContractCreationQuery",
    "ContractEventQuery",
    "ContractMethodQuery",
]


# TODO: Replace with `functools.cache` when Py3.8 dropped
@lru_cache(maxsize=None)
def _basic_columns(Model: Type[BaseInterfaceModel]) -> Set[str]:
    columns = set(Model.model_fields)

    # TODO: Remove once `ReceiptAPI` fields cleaned up for better processing
    if Model == ReceiptAPI:
        columns.remove("transaction")
        columns |= _basic_columns(TransactionAPI)

    return columns


# TODO: Replace with `functools.cache` when Py3.8 dropped
@lru_cache(maxsize=None)
def _all_columns(Model: Type[BaseInterfaceModel]) -> Set[str]:
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
    columns: Sequence[str], Model: Type[BaseInterfaceModel]
) -> List[str]:
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


def _unrecognized_columns(selected_columns: Set[str], all_columns: Set[str]) -> str:
    unrecognized = "', '".join(sorted(selected_columns - all_columns))
    all_cols = ", ".join(sorted(all_columns))
    return f"Unrecognized field(s) '{unrecognized}', must be one of '{all_cols}'."


def extract_fields(item: BaseInterfaceModel, columns: Sequence[str]) -> List[Any]:
    return [getattr(item, col, None) for col in columns]


class _BaseQuery(BaseModel):
    columns: Sequence[str]

    # TODO: Support "*" from getting the EcosystemAPI fields


class _BaseBlockQuery(_BaseQuery):
    start_block: NonNegativeInt = 0
    stop_block: NonNegativeInt
    step: PositiveInt = 1

    @model_validator(mode="before")
    @classmethod
    def check_start_block_before_stop_block(cls, values):
        if values["stop_block"] < values["start_block"]:
            raise ValueError(
                f"stop_block: '{values['stop_block']}' cannot be less than "
                f"start_block: '{values['start_block']}'."
            )

        return values


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
    def check_start_nonce_before_stop_nonce(cls, values: Dict) -> Dict:
        if values["stop_nonce"] < values["start_nonce"]:
            raise ValueError(
                f"stop_nonce: '{values['stop_nonce']}' cannot be less than "
                f"start_nonce: '{values['start_nonce']}'."
            )

        return values


class ContractCreationQuery(_BaseBlockQuery):
    contract: AddressType


class ContractEventQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects members from ``event`` over a range of
    logs emitted by ``contract`` between ``start_block`` and ``stop_block``.
    """

    contract: Union[List[AddressType], AddressType]
    event: EventABI
    search_topics: Optional[Dict[str, Any]] = None


class ContractMethodQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects return values from calling ``method`` in ``contract``
    over a range of blocks between ``start_block`` and ``stop_block``.
    """

    contract: AddressType
    method: MethodABI
    method_args: Dict[str, Any]


class QueryAPI(BaseInterface):
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
