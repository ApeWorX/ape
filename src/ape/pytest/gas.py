from typing import Optional

from ethpm_types.abi import MethodABI
from ethpm_types.source import ContractSource
from evm_trace.gas import merge_reports

from ape.api.trace import TraceAPI
from ape.pytest.config import ConfigWrapper
from ape.types.address import AddressType
from ape.types.trace import ContractFunctionPath, GasReport
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.trace import _exclude_gas, parse_gas_table


class GasTracker(ManagerAccessMixin):
    """
    Class for tracking gas-used per method called in the
    contracts in your test suite.
    """

    def __init__(self, config_wrapper: ConfigWrapper):
        self.config_wrapper = config_wrapper
        self.session_gas_report: Optional[GasReport] = None

    @property
    def enabled(self) -> bool:
        return self.config_wrapper.track_gas

    @property
    def gas_exclusions(self) -> list[ContractFunctionPath]:
        return self.config_wrapper.gas_exclusions

    def show_session_gas(self) -> bool:
        if not self.session_gas_report:
            return False

        tables = parse_gas_table(self.session_gas_report)
        self.chain_manager._reports.echo(*tables)
        return True

    def append_gas(self, trace: TraceAPI, contract_address: AddressType):
        contract_type = self.chain_manager.contracts.get(contract_address)
        if not contract_type:
            # Skip unknown contracts.
            return

        report = trace.get_gas_report(exclude=self.gas_exclusions)
        self._merge(report)

    def append_toplevel_gas(self, contract: ContractSource, method: MethodABI, gas_cost: int):
        exclusions = self.gas_exclusions or []
        if (contract_id := contract.contract_type.name) and not _exclude_gas(
            exclusions, contract_id, method.selector
        ):
            self._merge({contract_id: {method.selector: [gas_cost]}})

    def _merge(self, report: dict):
        session_report = self.session_gas_report or {}
        self.session_gas_report = merge_reports(session_report, report)
