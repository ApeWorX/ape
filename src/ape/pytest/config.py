from functools import cached_property
from typing import Any, Optional, Union

from _pytest.config import Config as PytestConfig

from ape.types.trace import ContractFunctionPath
from ape.utils.basemodel import ManagerAccessMixin


def _get_config_exclusions(config) -> list[ContractFunctionPath]:
    return [
        ContractFunctionPath(contract_name=x.contract_name, method_name=x.method_name)
        for x in config.exclude
    ]


class ConfigWrapper(ManagerAccessMixin):
    """
    A class aggregating settings choices from both the pytest command line
    as well as the ``ape-config.yaml`` file. Also serves as a wrapper around the
    Pytest config object for ease-of-use and code-sharing.
    """

    def __init__(self, pytest_config: PytestConfig):
        self.pytest_config = pytest_config

    @cached_property
    def supports_tracing(self) -> bool:
        return self.provider.supports_tracing

    @cached_property
    def interactive(self) -> bool:
        return self.pytest_config.getoption("interactive")

    @cached_property
    def network(self) -> str:
        return self.pytest_config.getoption("network")

    @cached_property
    def isolation(self) -> bool:
        return not self.pytest_config.getoption("disable_isolation")

    @cached_property
    def disable_warnings(self) -> bool:
        return self.pytest_config.getoption("--disable-warnings")

    @cached_property
    def disconnect_providers_after(self) -> bool:
        return self.ape_test_config.disconnect_providers_after

    @cached_property
    def ape_test_config(self):
        return self.config_manager.get_config("test")

    @cached_property
    def track_gas(self) -> bool:
        return self.pytest_config.getoption("--gas") or self.ape_test_config.gas.show

    @cached_property
    def track_coverage(self) -> bool:
        return self.pytest_config.getoption("--coverage") or self.ape_test_config.coverage.track

    @property
    def xml_coverage(self) -> Union[bool, dict]:
        return self.ape_test_config.coverage.reports.xml

    @property
    def html_coverage(self) -> Union[bool, dict]:
        return self.ape_test_config.coverage.reports.html

    @cached_property
    def show_internal(self) -> bool:
        return self.pytest_config.getoption("--show-internal")

    @cached_property
    def gas_exclusions(self) -> list[ContractFunctionPath]:
        """
        The combination of both CLI values and config values.
        """
        cli_value = self.pytest_config.getoption("--gas-exclude")
        exclusions = (
            [ContractFunctionPath.from_str(item) for item in cli_value.split(",")]
            if cli_value
            else []
        )
        paths = _get_config_exclusions(self.ape_test_config.gas)
        exclusions.extend(paths)
        return exclusions

    @cached_property
    def coverage_exclusions(self) -> list[ContractFunctionPath]:
        return _get_config_exclusions(self.ape_test_config.coverage)

    def get_pytest_plugin(self, name: str) -> Optional[Any]:
        if self.pytest_config.pluginmanager.has_plugin(name):
            return self.pytest_config.pluginmanager.get_plugin(name)

        return None
