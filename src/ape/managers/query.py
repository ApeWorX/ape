from typing import TYPE_CHECKING, Any, Dict, List, Optional

import pandas as pd
from pydantic import BaseModel

from ape.types import AddressType

if TYPE_CHECKING:
    from ape.types import Query


class BlockQuery(BaseModel):
    columns: List[str]
    start_block: int = 0
    stop_block: Optional[int] = None


class AccountQuery(BlockQuery):
    account: AddressType
    columns: List[str]
    start_nonce: int = 0
    stop_nonce: Optional[int] = None


class EventQuery(BlockQuery):
    contract: AddressType
    event_id: bytes
    columns: List[str]
    start_block: int = 0
    stop_block: Optional[int] = None
    filter_args: Dict[str, Any]


class MethodQuery(BaseModel):
    contract: AddressType
    method_id: bytes
    start_block: int = 0
    stop_block: Optional[int] = None
    # args


class QueryManager:
    """
    A singelton that manages all query sources.

    Args:
        query (``Query``): query to execute

    Returns:

    Usage example::

        chain.blocks.query()
    """

    def query(self, query: "Query") -> pd.DataFrame:
        """ """
        pass
