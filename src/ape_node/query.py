from collections.abc import Iterator
from functools import singledispatchmethod

from ape.api.query import (
    ContractCreation,
    ContractCreationQuery,
    CursorAPI,
    QueryEngineAPI,
)
from ape.types import AddressType


class ContractCreationCursor(CursorAPI):
    query: ContractCreationQuery

    def shrink(
        self,
        start_index: int | None = None,
        end_index: int | None = None,
    ) -> "ContractCreationCursor":
        start = self.query.start_index if start_index is None else start_index
        end = self.query.end_index if end_index is None else end_index
        if start != self.query.start_index or end != self.query.end_index:
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

    def as_model_iter(self) -> Iterator[ContractCreation]:
        yield self._get_ots_contract_creation()


class OtterscanQueryEngine(QueryEngineAPI):
    execute = singledispatchmethod(QueryEngineAPI.execute)

    @property
    def supports_ots_namespace(self) -> bool:
        return getattr(self.provider, "_ots_api_level", None) is not None

    @execute.register
    def exec_creation_query(self, query: ContractCreationQuery) -> Iterator[ContractCreationCursor]:
        if self.supports_ots_namespace:
            yield ContractCreationCursor(query=query)
