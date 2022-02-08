from typing import Any, Dict, List, Literal, Optional, Union

import pandas as pd
from pydantic import BaseModel

from ape.types import AddressType
from ape.utils import abstractdataclass, abstractmethod

Query = Union["BlockQuery", "AccountQuery", "ContractEventQuery", "ContractMethodQuery"]


class BaseQuery(BaseModel):
    type: str  # Used as discriminator
    columns: List[str]
    filter_args: Dict[str, Any]
    engine_to_use: Optional[str] = None


class BaseBlockQuery(BaseQuery):
    start_block: int = 0
    stop_block: Optional[int] = None


class BlockQuery(BaseBlockQuery):
    type: Literal["blocks"]


class BaseAccountQuery(BaseModel):
    start_nonce: int = 0
    stop_nonce: Optional[int] = None
    engine_to_use: Optional[str] = None


class AccountQuery(BaseBlockQuery):
    type: Literal["accounts"]
    account: AddressType


class ContractEventQuery(BaseBlockQuery):
    type: Literal["contract_events"]
    contract: AddressType
    event_id: bytes


class ContractMethodQuery(BaseBlockQuery):
    type: Literal["contract_calls"]
    contract: AddressType
    method_id: bytes
    method_args: Dict[str, Any]


@abstractdataclass
class QueryAPI:

    engine_to_use: Optional[str] = None

    @abstractmethod
    def estimate_query(self, query: Query) -> Optional[int]:
        """
        Estimation of time needed to complete the query.

        Args:
            query (``Query``): query to estimate

        Returns:
            pandas.DataFrame
        """

    @abstractmethod
    def perform_query(self, query: Query) -> pd.DataFrame:
        """
        Executes the query using best performing ``estimate_query`` query engine.

        Args:
            query (``Query``): query to execute

        Returns:
            pandas.DataFrame
        """
