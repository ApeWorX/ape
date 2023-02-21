from fnmatch import fnmatch
from typing import TYPE_CHECKING, Any, Dict, List, Optional

from evm_trace.gas import merge_reports
from pydantic import Field
from rich.table import Table
from rich.tree import Tree

from ape.utils.basemodel import BaseInterfaceModel
from ape.utils.trace import parse_as_str, parse_gas_table, parse_rich_tree

if TYPE_CHECKING:
    from ape.types import ContractFunctionPath


GasReport = Dict[str, Dict[str, List[int]]]
"""
A gas report in Ape.
"""


class CallTreeNode(BaseInterfaceModel):
    contract_id: str
    """
    The identifier representing the contract in this node.
    A non-enriched identifier is an address; a more enriched
    identifier is a token symbol or contract type name.
    """

    method_id: Optional[str] = None
    """
    The identifier representing the method in this node.
    A non-enriched identifier is a method selector.
    An enriched identifier is method signature.
    """

    txn_hash: Optional[str] = None
    """
    The transaction hash, if known and/or exists.
    """

    failed: bool = False
    """
    ``True`` where this tree represents a failed call.
    """

    inputs: Optional[Any] = None
    """
    The inputs to the call.
    Non-enriched inputs are raw bytes or values.
    Enriched inputs are decoded.
    """

    outputs: Optional[Any] = None
    """
    The output to the call.
    Non-enriched inputs are raw bytes or values.
    Enriched outputs are decoded.
    """

    value: Optional[int] = None
    """
    The value sent with the call, if applicable.
    """

    gas_cost: Optional[int] = None
    """
    The gas cost of the call, if known.
    """

    call_type: Optional[str] = None
    """
    A str indicating what type of call it is.
    See ``evm_trace.enums.CallType`` for EVM examples.
    """

    calls: List["CallTreeNode"] = []
    """
    The list of subcalls made by this call.
    """

    raw: Dict = Field({}, exclude=True, repr=False)
    """
    The raw tree, as a dictionary, associated with the call.
    """

    def __repr__(self) -> str:
        return parse_as_str(self)

    def __str__(self) -> str:
        return parse_as_str(self)

    def _repr_pretty_(self, *args, **kwargs):
        enriched_tree = self.enrich(use_symbol_for_tokens=True)
        self.chain_manager._reports.show_trace(enriched_tree)

    def enrich(self, **kwargs) -> "CallTreeNode":
        """
        Enrich the properties on this call tree using data from contracts
        and using information about the ecosystem.

        Args:
            **kwargs: Key-word arguments to pass to
              :meth:`~ape.api.networks.EcosystemAPI.enrich_calltree`, such as
              ``use_symbol_for_tokens``.

        Returns:
            :class:`~ape.types.trace.CallTreeNode`: This call tree node with
            its properties enriched.
        """

        return self.provider.network.ecosystem.enrich_calltree(self, **kwargs)

    def add(self, sub_call: "CallTreeNode"):
        """
        Add a sub call to this node. This implies this call called the sub-call.

        Args:
            sub_call (:class:`~ape.types.trace.CallTreeNode`): The sub-call to add.
        """

        self.calls.append(sub_call)

    def as_rich_tree(self, verbose: bool = False) -> Tree:
        """
        Return this object as a ``rich.tree.Tree`` for pretty-printing.

        Returns:
            ``Tree``
        """

        return parse_rich_tree(self, verbose=verbose)

    def as_gas_tables(self, exclude: Optional[List["ContractFunctionPath"]] = None) -> List[Table]:
        """
        Return this object as list of rich gas tables for pretty printing.

        Args:
            exclude (Optional[List[:class:`~ape.types.ContractFunctionPath`]]):
              A list of contract / method combinations to exclude from the gas
              tables.

        Returns:
            List[``rich.table.Table``]
        """

        report = self.get_gas_report(exclude=exclude)
        return parse_gas_table(report)

    def get_gas_report(self, exclude: Optional[List["ContractFunctionPath"]] = None) -> "GasReport":
        """
        Get a unified gas-report of all the calls made in this tree.

        Args:
            exclude (Optional[List[:class:`~ape.types.ContractFunctionPath`]]):
              A list of contract / method combinations to exclude from the gas
              tables.

        Returns:
            :class:`~ape.types.trace.GasReport`
        """

        exclusions = exclude or []

        for exclusion in exclusions:
            if exclusion.method_name is None and fnmatch(self.contract_id, exclusion.contract_name):
                # Skip this whole contract. Search contracts from sub-calls.
                return merge_reports(*(c.get_gas_report(exclude) for c in self.calls))

            for excl in exclusions:
                if not excl.method_name:
                    # Full contract skips handled above.
                    continue

                elif not fnmatch(self.contract_id, excl.contract_name):
                    # Method may match, but contract does not match, so continue.
                    continue

                elif self.method_id and fnmatch(self.method_id, excl.method_name):
                    # Skip this report because of the method name exclusion criteria.
                    return merge_reports(*(c.get_gas_report(exclude) for c in self.calls))

        reports = [c.get_gas_report(exclude) for c in self.calls]
        if self.method_id:
            report = {
                self.contract_id: {
                    self.method_id: [self.gas_cost] if self.gas_cost is not None else []
                }
            }
            reports.append(report)

        return merge_reports(*reports)


class TraceFrame(BaseInterfaceModel):
    """
    A low-level data structure modeling a transaction trace frame
    from the Geth RPC ``debug_traceTransaction``.
    """

    pc: int
    """Program counter."""

    op: str
    """Opcode."""

    gas: int
    """Remaining gas."""

    gas_cost: int
    """The cost to execute this opcode."""

    depth: int
    """
    The number of external jumps away the initially called contract (starts at 0).
    """

    raw: Dict = Field({}, exclude=True, repr=False)
    """
    The raw trace frame from the provider.
    """
