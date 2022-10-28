from typing import Any, Dict, List

from _pytest.config import Config as PytestConfig

from ape.utils import ManagerAccessMixin, cached_property


class ConfigWrapper(ManagerAccessMixin):
    """
    A class aggregating settings choices from both the pytest command line
    as well as the `ape-config.yaml` file. Also serves as a wrapper around the
    Pytest config object for ease-of-use and code-sharing.
    """

    def __init__(self, pytest_config: PytestConfig):
        self.pytest_config = pytest_config

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
    def ape_test_config(self):
        return self.config_manager.get_config("test")

    @cached_property
    def track_gas(self) -> bool:
        return self.pytest_config.getoption("--gas") or self.ape_test_config.gas.show

    @cached_property
    def gas_exclusions(self) -> List[Dict]:
        """
        The combination of both CLI values and config values.
        """

        cli_value = self.pytest_config.getoption("--gas-exclude")
        exclusions = []
        if cli_value:
            items = cli_value.split(",")
            for item in items:
                if ":" in item:
                    contract_name, method_name = item.split(":")
                    exclusion = {"contract": contract_name, "method": method_name}
                else:
                    exclusion = {"contract": item}

                exclusions.append(exclusion)

        config_value = self.ape_test_config.gas.exclude
        exclusions.extend([x.dict() for x in config_value])

        filtered_exclusions = []
        for exclusion in exclusions:
            if exclusion not in filtered_exclusions:
                filtered_exclusions.append(exclusion)

        return filtered_exclusions

    def get_pytest_plugin(self, name: str) -> Any:
        return self.pytest_config.pluginmanager.get_plugin(name)
