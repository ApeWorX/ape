from functools import singledispatchmethod
from typing import Iterator, Optional

from ape.api import ReceiptAPI
from ape.api.query import ContractCreationQuery, QueryAPI, QueryType
from ape.exceptions import QueryEngineError
from ape_geth.provider import BaseGethProvider


class OTSQueryEngine(QueryAPI):
    @singledispatchmethod
    def estimate_query(self, query: QueryType) -> Optional[int]:  # type: ignore[override]
        return None

    @singledispatchmethod
    def perform_query(self, query: QueryType) -> Iterator:  # type: ignore[override]
        raise QueryEngineError(
            f"{self.__class__.__name__} cannot handle {query.__class__.__name__} queries."
        )

    @estimate_query.register
    def estimate_contract_creation_query(self, query: ContractCreationQuery) -> Optional[int]:
        if self.network_manager.active_provider:
            if not isinstance(self.provider, BaseGethProvider):
                return None

        # About 225 ms per query
        return 225

    @perform_query.register
    def get_contract_creation_receipt(self, query: ContractCreationQuery) -> Iterator[ReceiptAPI]:
        if self.network_manager.active_provider and isinstance(self.provider, BaseGethProvider):
            if receipt := self.provider._get_contract_creation_receipt(query.contract):
                yield receipt
