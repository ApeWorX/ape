from typing import Any, Dict, List, Literal, Optional, Union

import pandas as pd
from pydantic import BaseModel, PositiveInt, root_validator

from ape.managers.networks import NetworkManager
from ape.types import AddressType
from ape.utils import abstractdataclass, abstractmethod

QueryType = Union["BlockQuery", "AccountQuery", "ContractEventQuery", "ContractMethodQuery"]


class _BaseQuery(BaseModel):
    type: str  # Used as discriminator
    columns: Union[str, List[str]]


class _BaseBlockQuery(_BaseQuery):
    start_block: PositiveInt = 0
    stop_block: PositiveInt

    @root_validator(pre=True)
    def check_start_block_before_stop_block(cls, values):
        if values["stop_block"] < values["start_block"]:
            raise ValueError(
                f"stop_block: {values['stop_block']} cannot be less than "
                f"start_block: {values['start_block']}."
            )

        return values


class BlockQuery(_BaseBlockQuery):
    type: Literal["blocks"]


class _BaseAccountQuery(BaseModel):
    start_nonce: PositiveInt = 0
    stop_nonce: PositiveInt

    @root_validator(pre=True)
    def check_start_nonce_before_stop_nonce(cls, values):
        if values["stop_nonce"] < values["start_nonce"]:
            raise ValueError(
                f"stop_nonce: {values['stop_nonce']} cannot be less than "
                f"start_nonce: {values['start_nonce']}."
            )

        return values


class AccountQuery(_BaseAccountQuery):
    type: Literal["accounts"]
    account: AddressType


class ContractEventQuery(_BaseBlockQuery):
    type: Literal["contract_events"]
    contract: AddressType
    event_id: bytes


class ContractMethodQuery(_BaseBlockQuery):
    type: Literal["contract_calls"]
    contract: AddressType
    method_id: bytes
    method_args: Dict[str, Any]


@abstractdataclass
class QueryAPI:

    network_manager: NetworkManager

    @abstractmethod
    def estimate_query(self, query: QueryType) -> Optional[int]:
        """
        Estimation of time needed to complete the query. The estimation is returned
        as an int representing milliseconds. A value of None indicates that the
        query engine is not available for use.

        Args:
            query (``QueryType``): query to estimate

        Returns:
            Optional[int]: Represents milliseconds, returns ``None`` if unavailable.

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
