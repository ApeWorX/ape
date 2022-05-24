from typing import Any, Dict, Iterator, List, Optional, Union

from ethpm_types.abi import EventABI, MethodABI
from pydantic import BaseModel, NonNegativeInt, PositiveInt, root_validator, validator

from ape.types import AddressType
from ape.utils import BaseInterfaceModel, abstractmethod

from .transactions import TransactionAPI

QueryType = Union[
    "BlockQuery",
    "BlockTransactionQuery",
    "AccountTransactionQuery",
    "ContractEventQuery",
    "ContractMethodQuery",
]


class _BaseQuery(BaseModel):

    columns: List[str]

    @classmethod
    @abstractmethod
    def all_fields(cls) -> List[str]:
        """
        Validates fields that are called during a block query.

        Returns:
            List[str]: list of keys to be returned during block query.
        """

    @validator("columns")
    def check_columns(cls, data: List[str]) -> List[str]:
        all_fields = cls.all_fields()
        if len(data) == 1 and data[0] == "*":
            return all_fields
        else:
            if len(set(data)) != len(data):
                raise ValueError(f"Duplicate fields in {data}")
            for d in data:
                if d not in all_fields:
                    raise ValueError(f"Unrecognized field '{d}', must be one of {all_fields}")
        return data


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

    @classmethod
    def all_fields(cls) -> List[str]:
        from .providers import BlockAPI

        return list(BlockAPI.__fields__)


class BlockTransactionQuery(_BaseQuery):
    """
    A ``QueryType`` that collects properties of ``TransactionAPI`` over a range of
    transactions collected inside the ``BlockAPI` object represented by ``block_id``.
    """

    block_id: Any

    @classmethod
    def all_fields(cls) -> List[str]:
        return list(TransactionAPI.__fields__)


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

    @classmethod
    def all_fields(cls) -> List[str]:
        return list(TransactionAPI.__fields__)


class ContractEventQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects members from ``event`` over a range of
    logs emitted by ``contract`` between ``start_block`` and ``stop_block``.
    """

    contract: AddressType
    event: EventABI

    @classmethod
    def all_fields(cls) -> List[str]:
        # TODO: Figure out how to get the event ABI as a class property
        #   for the validator
        return [
            i.name for i in cls.event.inputs if i.name is not None
        ]  # if i.name is not None just for mypy


class ContractMethodQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects return values from calling ``method`` in ``contract``
    over a range of blocks between ``start_block`` and ``stop_block``.
    """

    contract: AddressType
    method: MethodABI
    method_args: Dict[str, Any]

    @classmethod
    def all_fields(cls) -> List[str]:
        # TODO: Figure out how to get the method ABI as a class property
        #   for the validator
        return [o.name for o in cls.method.outputs if o.name is not None]  # just for mypy


class QueryAPI(BaseInterfaceModel):
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

    def update_cache(self, query: QueryType, result: Iterator):
        """
        Allows a query plugin the chance to update any cache using the results obtained
        from other query plugins. Defaults to doing nothing, override to store cache data.

        Args:
            query (``QueryType``): query that was executed
            result (``Iterator``): the result of the query
        """
