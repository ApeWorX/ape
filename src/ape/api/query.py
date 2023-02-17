from typing import Any, Dict, Iterator, List, Optional, Type, Union

from ethpm_types.abi import EventABI, MethodABI
from pydantic import BaseModel, NonNegativeInt, PositiveInt, root_validator

from ape.logging import logger
from ape.types import AddressType
from ape.utils import BaseInterface, BaseInterfaceModel, abstractmethod, cached_property

QueryType = Union[
    "BlockQuery",
    "BlockTransactionQuery",
    "AccountTransactionQuery",
    "ContractEventQuery",
    "ContractMethodQuery",
]


def validate_and_expand_columns(columns: List[str], Model: Type[BaseInterfaceModel]) -> List[str]:
    if len(columns) == 1 and columns[0] == "*":
        # NOTE: By default, only pull explicit fields
        #       (because they are cheap to pull, but properties might not be)
        return list(Model.__fields__)

    else:
        deduped_columns = set(columns)
        if len(deduped_columns) != len(columns):
            logger.warning(f"Duplicate fields in {columns}")

        all_columns = set(Model.__fields__)
        # NOTE: Iterate down the series of subclasses of `Model` (e.g. Block and BlockAPI)
        #       and get all of the public property methods of each class (which are valid columns)
        all_columns.update(
            {
                field
                for cls in Model.__mro__
                if issubclass(cls, BaseInterfaceModel) and cls != BaseInterfaceModel
                for field in vars(cls)
                if not field.startswith("_")
                and isinstance(vars(cls)[field], (property, cached_property))
            }
        )

        if len(deduped_columns - all_columns) > 0:
            unrecognized = "', '".join(deduped_columns - all_columns)
            logger.warning(f"Unrecognized field(s) '{unrecognized}', must be one of {all_columns}")

        selected_fields = all_columns.intersection(deduped_columns)
        if len(selected_fields) > 0:
            return list(selected_fields)

    raise ValueError(f"No valid fields in {columns}.")


def extract_fields(item, columns):
    return [getattr(item, col) for col in columns]


class _BaseQuery(BaseModel):
    columns: List[str]

    # TODO: Support "*" from getting the EcosystemAPI fields


class _BaseBlockQuery(_BaseQuery):
    start_block: NonNegativeInt = 0
    stop_block: NonNegativeInt
    step: PositiveInt = 1

    @root_validator(pre=True)
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

    @root_validator(pre=True)
    def check_start_nonce_before_stop_nonce(cls, values: Dict) -> Dict:
        if values["stop_nonce"] < values["start_nonce"]:
            raise ValueError(
                f"stop_nonce: '{values['stop_nonce']}' cannot be less than "
                f"start_nonce: '{values['start_nonce']}'."
            )

        return values


class ContractEventQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects members from ``event`` over a range of
    logs emitted by ``contract`` between ``start_block`` and ``stop_block``.
    """

    contract: Union[AddressType, List[AddressType]]
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
