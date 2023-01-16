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
    method_id: Optional[str] = None
    failed: bool = False
    inputs: Optional[Any] = None
    outputs: Optional[Any] = None
    value: Optional[int] = None
    gas_cost: Optional[int] = None
    raw_tree: Dict = {}
    call_type: Optional[str] = None
    calls: List["CallTreeNode"] = []
    raw: Dict = Field({}, exclude=True, repr=False)

    def __repr__(self) -> str:
        return parse_as_str(self)

    def __str__(self) -> str:
        return parse_as_str(self)

    def _repr_pretty_(self, *args, **kwargs) -> str:
        return parse_as_str(self.enrich(), stylize=True)

    def enrich(self):
        self.provider.network.ecosystem.enrich_calltree(self)

    def add(self, sub: "CallTreeNode"):
        self.calls.append(sub)

    def as_rich_tree(self) -> Tree:
        return parse_rich_tree(self)

    def as_gas_tables(self, exclude: Optional[List["ContractFunctionPath"]] = None) -> List[Table]:
        report = self.get_gas_report(exclude=exclude)
        return parse_gas_table(report)

    def get_gas_report(self, exclude: Optional[List["ContractFunctionPath"]] = None) -> "GasReport":
        exclusions = exclude or []

        for exclusion in exclusions:
            if exclusion.method_name is None and fnmatch(self.contract_id, exclusion.contract_name):
                # Skip this whole contract. Search contracts from sub-calls.
                return _merge_gas_reports(*[c.get_gas_report(exclude) for c in self.calls])

            for excl in exclusions:
                if not excl.method_name:
                    # Full contract skips handled above.
                    continue

                elif not fnmatch(self.contract_id, excl.contract_name):
                    # Method may match, but contract does not match, so continue.
                    continue

                elif self.method_id and fnmatch(self.method_id, excl.method_name):
                    # Skip this report because of the method name exclusion criteria.
                    return _merge_gas_reports(*[c.get_gas_report(exclude) for c in self.calls])

        reports = [c.get_gas_report(exclude) for c in self.calls]
        if self.method_id:
            report = {
                self.contract_id: {
                    self.method_id: [self.gas_cost] if self.gas_cost is not None else []
                }
            }
            reports.append(report)

        return _merge_gas_reports(*reports)


def _merge_gas_reports(*reports: GasReport) -> GasReport:
    if len(reports) == 1:
        return reports[0]
    elif len(reports) > 1:
        return merge_reports(*reports)

    return {}


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
