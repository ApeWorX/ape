from collections.abc import Iterator
from functools import singledispatchmethod
from typing import TYPE_CHECKING, Optional

import narwhals as nw

from ape.api.query import (
    ContractCreation,
    ContractCreationQuery,
    CursorAPI,
    QueryEngineAPI,
    QueryType,
)
from ape.exceptions import QueryEngineError
from ape.types import AddressType
from ape_ethereum.provider import EthereumNodeProvider

if TYPE_CHECKING:
    from narwhals.typing import Frame


class ContractCreationCursor(CursorAPI):
    query: ContractCreationQuery

    def shrink(
        self,
        start_index: Optional[int] = None,
        end_index: Optional[int] = None,
    ) -> "ContractCreationCursor":
        if start_index or end_index:
            raise NotImplementedError

        return self

    @property
    def total_time(self) -> float:
        return 0.25

    @property
    def time_per_row(self) -> float:
        return 0.25

    def _get_ots_contract_creation(self) -> ContractCreation:
        result = self.provider.make_request("ots_getContractCreator", [self.query.contract])
        creator = self.conversion_manager.convert(result["creator"], AddressType)
        receipt = self.provider.get_receipt(result["hash"])
        return ContractCreation(
            txn_hash=result["hash"],
            block=receipt.block_number,
            deployer=receipt.sender,
            factory=creator if creator != receipt.sender else None,
        )

    def as_dataframe(self, backend: nw.Implementation) -> "Frame":
        return nw.from_dict(self._get_ots_contract_creation().model_dump(), backend=backend)

    def as_model_iter(self) -> Iterator[ContractCreation]:
        yield self._get_ots_contract_creation()


class OtterscanQueryEngine(QueryEngineAPI):
    @singledispatchmethod
    def exec(self, query: QueryType) -> Iterator[CursorAPI]:  # type: ignore[override]
        return super().exec(query)

    @property
    def supports_ots_namespace(self) -> bool:
        return getattr(self.provider, "_ots_api_level", None) is not None

    @exec.register
    def exec_creation_query(self, query: ContractCreationQuery) -> Iterator[ContractCreationCursor]:
        if self.supports_ots_namespace:
            yield ContractCreationCursor(query=query)

    # TODO: Delete below in v0.9
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
        if getattr(self.provider, "_ots_api_level", None) is not None:
            return 250
        return None

    @perform_query.register
    def get_contract_creation_receipt(
        self, query: ContractCreationQuery
    ) -> Iterator[ContractCreation]:
        if self.network_manager.active_provider and isinstance(self.provider, EthereumNodeProvider):
            ots = self.provider.make_request("ots_getContractCreator", [query.contract])
            if ots is None:
                return None
            creator = self.conversion_manager.convert(ots["creator"], AddressType)
            receipt = self.provider.get_receipt(ots["hash"])
            yield ContractCreation(
                txn_hash=ots["hash"],
                block=receipt.block_number,
                deployer=receipt.sender,
                factory=creator if creator != receipt.sender else None,
            )
