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
from ape.exceptions import APINotImplementedError, ProviderError, QueryEngineError
from ape.types import AddressType

if TYPE_CHECKING:
    from narwhals.typing import Frame

    try:
        # Only on Python 3.11
        from typing import Self  # type: ignore
    except ImportError:
        from typing_extensions import Self  # type: ignore


class ContractCreationCursor(CursorAPI[ContractCreation]):
    query: ContractCreationQuery

    use_debug_trace: bool

    def shrink(
        self,
        start_index: Optional[int] = None,
        end_index: Optional[int] = None,
    ) -> "Self":
        if (start_index is not None and start_index != self.query.start_index) or (
            end_index is not None and end_index != self.query.end_index
        ):
            raise NotImplementedError

        return self

    @property
    def total_time(self) -> float:
        # NOTE: 1 row
        return self.time_per_row

    @property
    def time_per_row(self) -> float:
        # NOTE: Extremely expensive query, involves binary search of all blocks in a chain
        #       Very loose estimate of 5s per call for this query.
        return 5.0

    def _find_creation_in_block_via_parity(self, block, contract_address):
        # NOTE requires `trace_` namespace
        traces = self.provider.make_request("trace_replayBlockTransactions", [block, ["trace"]])

        for tx in traces:
            for trace in tx["trace"]:
                if (
                    "error" not in trace
                    and trace["type"] == "create"
                    and trace["result"]["address"] == contract_address.lower()
                ):
                    receipt = self.chain_manager.get_receipt(tx["transactionHash"])
                    creator = self.conversion_manager.convert(trace["action"]["from"], AddressType)
                    yield ContractCreation(
                        txn_hash=tx["transactionHash"],
                        block=block,
                        deployer=receipt.sender,
                        factory=creator if creator != receipt.sender else None,
                    )

    def _find_creation_in_block_via_geth(self, block, contract_address):
        # NOTE requires `debug_` namespace
        traces = self.provider.make_request(
            "debug_traceBlockByNumber", [hex(block), {"tracer": "callTracer"}]
        )

        def flatten(call):
            if call["type"] in ["CREATE", "CREATE2"]:
                yield call["from"], call["to"]

            if "error" in call or "calls" not in call:
                return

            for sub in call["calls"]:
                if sub["type"] in ["CREATE", "CREATE2"]:
                    yield sub["from"], sub["to"]
                else:
                    yield from flatten(sub)

        for tx in traces:
            call = tx["result"]
            sender = call["from"]
            for factory, contract in flatten(call):
                if contract == contract_address.lower():
                    yield ContractCreation(
                        txn_hash=tx["txHash"],
                        block=block,
                        deployer=self.conversion_manager.convert(sender, AddressType),
                        factory=(
                            self.conversion_manager.convert(factory, AddressType)
                            if factory != sender
                            else None
                        ),
                    )

    def as_model_iter(self) -> Iterator[ContractCreation]:
        # skip the search if there is still no code at address at head
        if not self.chain_manager.get_code(self.query.contract):
            return None

        def find_creation_block(lo, hi):
            # perform a binary search to find the block when the contract was deployed.
            # takes log2(height), doesn't work with contracts that have been reinit.
            while hi - lo > 1:
                mid = (lo + hi) // 2
                code = self.chain_manager.get_code(self.query.contract, block_id=mid)
                if not code:
                    lo = mid
                else:
                    hi = mid

            if self.chain_manager.get_code(self.query.contract, block_id=hi):
                return hi

            return None

        if not (block := find_creation_block(0, self.chain_manager.blocks.height)):
            return

        if self.use_debug_trace:
            yield from self._find_creation_in_block_via_geth(block, self.query.contract)

        else:
            yield from self._find_creation_in_block_via_parity(block, self.query.contract)

    def as_dataframe(self, backend: nw.Implementation) -> "Frame":
        data: dict[str, list] = {column: [] for column in self.query.columns}

        # NOTE: Only 1 item
        item = next(self.as_model_iter())
        for column in data:
            data[column] = getattr(item, column)

        return nw.from_dict(data, backend=backend)


class EthereumQueryProvider(QueryEngineAPI):
    """
    Implements more advanced queries specific to Ethereum clients.
    """

    def _has_method(self, rpc_method: str) -> bool:
        try:
            self.provider.make_request(rpc_method, [])
            return True

        except APINotImplementedError:
            return False

        except ProviderError as e:
            return "Method not found" not in str(e)

    @property
    def use_debug_trace(self) -> bool:
        return "geth" in self.provider.client_version.lower() and self._has_method(
            "debug_traceBlockByNumber"
        )

    @property
    def use_trace_replay(self) -> bool:
        return self._has_method("trace_replayBlockTransactions")

    @singledispatchmethod
    def exec(self, query: QueryType) -> Iterator[CursorAPI]:  # type: ignore[override]
        return super().exec(query)

    @exec.register
    def exec_contract_creation(
        self, query: ContractCreationQuery
    ) -> Iterator[ContractCreationCursor]:
        if (use_debug_trace := self.use_debug_trace) or self.use_trace_replay:
            yield ContractCreationCursor(query=query, use_debug_trace=use_debug_trace)

    # TODO: Delete all of below in v0.9
    def __init__(self):
        self.supports_contract_creation = None  # will be set after we try for the first time

    @singledispatchmethod
    def estimate_query(self, query: QueryType) -> Optional[int]:  # type: ignore[override]
        return None

    @singledispatchmethod
    def perform_query(self, query: QueryType) -> Iterator:  # type: ignore[override]
        raise QueryEngineError(f"Cannot handle '{type(query)}'.")

    @estimate_query.register
    def estimate_contract_creation_query(self, query: ContractCreationQuery) -> Optional[int]:
        # NOTE: Extremely expensive query, involves binary search of all blocks in a chain
        #       Very loose estimate of 5s per transaction for this query.
        if self.supports_contract_creation is False:
            return None
        return 5000

    @perform_query.register
    def perform_contract_creation_query(
        self, query: ContractCreationQuery
    ) -> Iterator[ContractCreation]:
        """
        Find when a contract was deployed using binary search and block tracing.
        """
        # skip the search if there is still no code at address at head
        if not self.chain_manager.get_code(query.contract):
            return None

        def find_creation_block(lo, hi):
            # perform a binary search to find the block when the contract was deployed.
            # takes log2(height), doesn't work with contracts that have been reinit.
            while hi - lo > 1:
                mid = (lo + hi) // 2
                code = self.chain_manager.get_code(query.contract, block_id=mid)
                if not code:
                    lo = mid
                else:
                    hi = mid

            if self.chain_manager.get_code(query.contract, block_id=hi):
                return hi

            return None

        try:
            block = find_creation_block(0, self.chain_manager.blocks.height)
        except ProviderError:
            self.supports_contract_creation = False
            return None

        # iterate over block transaction traces to find the deployment call
        # this method also supports contracts created by factories
        try:
            if "geth" in self.provider.client_version.lower():
                yield from self._find_creation_in_block_via_geth(block, query.contract)
            else:
                yield from self._find_creation_in_block_via_parity(block, query.contract)
        except (ProviderError, APINotImplementedError):
            self.supports_contract_creation = False
            return None

        self.supports_contract_creation = True

    def _find_creation_in_block_via_parity(self, block, contract_address):
        # NOTE requires `trace_` namespace
        traces = self.provider.make_request("trace_replayBlockTransactions", [block, ["trace"]])

        for tx in traces:
            for trace in tx["trace"]:
                if (
                    "error" not in trace
                    and trace["type"] == "create"
                    and trace["result"]["address"] == contract_address.lower()
                ):
                    receipt = self.chain_manager.get_receipt(tx["transactionHash"])
                    creator = self.conversion_manager.convert(trace["action"]["from"], AddressType)
                    yield ContractCreation(
                        txn_hash=tx["transactionHash"],
                        block=block,
                        deployer=receipt.sender,
                        factory=creator if creator != receipt.sender else None,
                    )

    def _find_creation_in_block_via_geth(self, block, contract_address):
        # NOTE requires `debug_` namespace
        traces = self.provider.make_request(
            "debug_traceBlockByNumber", [hex(block), {"tracer": "callTracer"}]
        )

        def flatten(call):
            if call["type"] in ["CREATE", "CREATE2"]:
                yield call["from"], call["to"]

            if "error" in call or "calls" not in call:
                return

            for sub in call["calls"]:
                if sub["type"] in ["CREATE", "CREATE2"]:
                    yield sub["from"], sub["to"]
                else:
                    yield from flatten(sub)

        for tx in traces:
            call = tx["result"]
            sender = call["from"]
            for factory, contract in flatten(call):
                if contract == contract_address.lower():
                    yield ContractCreation(
                        txn_hash=tx["txHash"],
                        block=block,
                        deployer=self.conversion_manager.convert(sender, AddressType),
                        factory=(
                            self.conversion_manager.convert(factory, AddressType)
                            if factory != sender
                            else None
                        ),
                    )
