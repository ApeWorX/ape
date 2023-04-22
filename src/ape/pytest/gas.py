from typing import List, Optional

from evm_trace.gas import merge_reports

from ape.pytest.config import ConfigWrapper
from ape.types import AddressType, CallTreeNode, ContractFunctionPath, GasReport
from ape.utils import parse_gas_table
from ape.utils.basemodel import ManagerAccessMixin


class GasTracker(ManagerAccessMixin):
    """
    Class for tracking gas-used per method called in the
    contracts in your test suite.
    """

    def __init__(self, config_wrapper: ConfigWrapper):
        self.config_wrapper = config_wrapper
        self.session_gas_report: Optional[GasReport] = None

    @property
    def track_gas(self) -> bool:
        return self.config_wrapper.track_gas

    @property
    def gas_exclusions(self) -> List[ContractFunctionPath]:
        return self.config_wrapper.gas_exclusions

    def show_session_gas(self) -> bool:
        if not self.session_gas_report:
            return False

        tables = parse_gas_table(self.session_gas_report)
        self.chain_manager._reports.echo(*tables)
        return True

    def append_gas(
        self,
        call_tree: CallTreeNode,
        contract_address: AddressType,
    ):
        contract_type = self.chain_manager.contracts.get(contract_address)
        if not contract_type:
            # Skip unknown contracts.
            return

        gas_report = call_tree.get_gas_report(exclude=self.gas_exclusions)
        session_report = self.session_gas_report or {}
        self.session_gas_report = merge_reports(session_report, gas_report)
