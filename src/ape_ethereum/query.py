from collections.abc import Iterator
from functools import singledispatchmethod
from typing import TYPE_CHECKING

from ape.api.query import (
    ContractCreation,
    ContractCreationQuery,
    CursorAPI,
    QueryEngineAPI,
)
from ape.exceptions import APINotImplementedError, ProviderError
from ape.types import AddressType

if TYPE_CHECKING:
    try:
        # Only on Python 3.11
        from typing import Self  # type: ignore
    except ImportError:
        from typing_extensions import Self  # type: ignore


class ContractCreationCursor(CursorAPI[ContractCreation]):
    query: ContractCreationQuery

    use_debug_trace: bool = False

    def shrink(
        self,
        start_index: int | None = None,
        end_index: int | None = None,
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

    def _has_method(self, rpc_method: str) -> bool:
        try:
            self.provider.make_request(rpc_method, [])
            return True
        except APINotImplementedError:
            return False
        except ProviderError as err:
            return "Method not found" not in str(err)

    def as_model_iter(self) -> Iterator[ContractCreation]:
        # Probes run only if this cursor is selected, so a missing trace API
        # does not abort planning for every other engine.
        try:
            client = self.provider.client_version.lower()
            use_debug = "geth" in client and self._has_method("debug_traceBlockByNumber")
            use_parity = self._has_method("trace_replayBlockTransactions")
        except (APINotImplementedError, AttributeError, ProviderError):
            return

        if not use_debug and not use_parity:
            return

        # skip the search if there is still no code at address at head
        if not self.chain_manager.get_code(self.query.contract):
            return

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

        try:
            block = find_creation_block(0, self.chain_manager.blocks.height)
        except ProviderError:
            return

        if block is None:
            return

        try:
            if use_debug:
                yield from self._find_creation_in_block_via_geth(block, self.query.contract)
            else:
                yield from self._find_creation_in_block_via_parity(block, self.query.contract)
        except (ProviderError, APINotImplementedError):
            return


class EthereumQueryProvider(QueryEngineAPI):
    """
    Implements more advanced queries specific to Ethereum clients.
    """

    execute = singledispatchmethod(QueryEngineAPI.execute)

    @execute.register
    def exec_contract_creation(
        self, query: ContractCreationQuery
    ) -> Iterator[ContractCreationCursor]:
        # Trace support is checked when the cursor runs, not while planning.
        yield ContractCreationCursor(query=query)
