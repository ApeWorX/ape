from collections.abc import Iterator
from functools import singledispatchmethod
from typing import Optional

from ape.api.query import ContractCreation, ContractCreationQuery, QueryAPI, QueryType
from ape.exceptions import APINotImplementedError, ProviderError, QueryEngineError
from ape.types.address import AddressType


class EthereumQueryProvider(QueryAPI):
    """
    Implements more advanced queries specific to Ethereum clients.
    """

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
        if not self.provider.get_code(query.contract):
            return None

        def find_creation_block(lo, hi):
            # perform a binary search to find the block when the contract was deployed.
            # takes log2(height), doesn't work with contracts that have been reinit.
            while hi - lo > 1:
                mid = (lo + hi) // 2
                code = self.provider.get_code(query.contract, block_id=mid)
                if not code:
                    lo = mid
                else:
                    hi = mid

            if self.provider.get_code(query.contract, block_id=hi):
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
