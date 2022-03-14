from typing import Any, Dict, List, Optional, Union

import pandas as pd
from ethpm_types.abi import EventABI, MethodABI
from pydantic import BaseModel, NonNegativeInt, root_validator

from ape._compat import Literal
from ape.types import AddressType
from ape.utils import BaseInterfaceModel, abstractmethod

QueryType = Union["BlockQuery", "AccountQuery", "ContractEventQuery", "ContractMethodQuery"]


class _BaseQuery(BaseModel):
    type: str  # Used as discriminator
    columns: List[str]


class _BaseBlockQuery(_BaseQuery):
    start_block: NonNegativeInt = 0
    stop_block: NonNegativeInt

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

    type: Literal["blocks"] = "blocks"


class _BaseAccountQuery(BaseModel):
    start_nonce: NonNegativeInt = 0
    stop_nonce: NonNegativeInt

    @root_validator(pre=True)
    def check_start_nonce_before_stop_nonce(cls, values):
        if values["stop_nonce"] < values["start_nonce"]:
            raise ValueError(
                f"stop_nonce: '{values['stop_nonce']}' cannot be less than "
                f"start_nonce: '{values['start_nonce']}'."
            )

        return values


class AccountQuery(_BaseAccountQuery):
    """
    A ``QueryType`` that collects properties of ``TransactionAPI`` over a range
    of transactions made by ``account`` between ``start_nonce`` and ``stop_nonce``.
    """

    type: Literal["accounts"] = "accounts"
    account: AddressType


class ContractEventQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects members from ``event`` over a range of
    logs emitted by ``contract`` between ``start_block`` and ``stop_block``.
    """

    type: Literal["contract_events"] = "contract_events"
    contract: AddressType
    event: EventABI


class ContractMethodQuery(_BaseBlockQuery):
    """
    A ``QueryType`` that collects return values from calling ``method`` in ``contract``
    over a range of blocks between ``start_block`` and ``stop_block``.
    """

    type: Literal["contract_calls"] = "contract_calls"
    contract: AddressType
    method: MethodABI
    method_args: Dict[str, Any]


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
    def perform_query(self, query: QueryType) -> pd.DataFrame:
        """
        Executes the query using best performing ``estimate_query`` query engine.

        Args:
            query (``QueryType``): query to execute

        Returns:
            pandas.DataFrame
        """

    def update_cache(self, query: QueryType, result: pd.DataFrame):
        """
        Allows a query plugin the chance to update any cache using the results obtained
        from other query plugins. Defaults to doing nothing, override to store cache data.

        Args:
            query (``QueryType``): query that was executed
            result (``pandas.DataFrame``): the result of the query
        """
