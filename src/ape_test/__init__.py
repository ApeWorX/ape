from typing import Dict, List, NewType, Optional, Union

from ape import plugins
from ape._pydantic_compat import NonNegativeInt
from ape.api import PluginConfig
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.utils import DEFAULT_HD_PATH, DEFAULT_NUMBER_OF_TEST_ACCOUNTS, DEFAULT_TEST_MNEMONIC
from ape_test.accounts import TestAccount, TestAccountContainer
from ape_test.provider import EthTesterProviderConfig, LocalProvider


class GasExclusion(PluginConfig):
    contract_name: str = "*"  # If only given method, searches across all contracts.
    method_name: Optional[str] = None  # By default, match all methods in a contract


CoverageExclusion = NewType("CoverageExclusion", GasExclusion)


class GasConfig(PluginConfig):
    """
    Configuration related to test gas reports.
    """

    show: bool = False
    """
    Set to ``True`` to always show gas.
    """

    exclude: List[GasExclusion] = []
    """
    Contract methods patterns to skip. Specify ``contract_name:`` and not
    ``method_name:`` to skip all methods in the contract. Only specify
    ``method_name:`` to skip all methods across all contracts. Specify
    both to skip methods in a certain contracts. Entries use glob-rules;
    use ``prefix_*`` to skip all items with a certain prefix.
    """


"""Dict is for extra report settings."""
_ReportType = Union[bool, Dict]


class CoverageReportsConfig(PluginConfig):
    """
    Enable reports.
    """

    terminal: _ReportType = True
    """
    Set to ``False`` to hide the terminal coverage report.
    """

    xml: _ReportType = False
    """
    Set to ``True`` to generate an XML coverage report in your .build folder.
    """

    html: _ReportType = False
    """
    Set to ``True`` to generate HTML coverage reports.
    """

    @property
    def has_any(self) -> bool:
        return any(x not in ({}, None, False) for x in (self.html, self.terminal, self.xml))


class CoverageConfig(PluginConfig):
    """
    Configuration related to contract coverage.
    """

    track: bool = False
    """
    Setting this to ``True`` is the same as always running with
    the ``--coverage`` flag.
    """

    reports: CoverageReportsConfig = CoverageReportsConfig()
    """
    Enable reports.
    """

    exclude: List[CoverageExclusion] = []
    """
    Contract methods patterns to skip. Specify ``contract_name:`` and not
    ``method_name:`` to skip all methods in the contract. Only specify
    ``method_name:`` to skip all methods across all contracts. Specify
    both to skip methods in a certain contracts. Entries use glob-rules;
    use ``prefix_*`` to skip all items with a certain prefix.
    """


class Config(PluginConfig):
    mnemonic: str = DEFAULT_TEST_MNEMONIC
    """
    The mnemonic to use when generating the test accounts.
    """

    number_of_accounts: NonNegativeInt = DEFAULT_NUMBER_OF_TEST_ACCOUNTS
    """
    The number of test accounts to generate in the provider.
    """

    gas: GasConfig = GasConfig()
    """
    Configuration related to gas reporting.
    """

    coverage: CoverageConfig = CoverageConfig()
    """
    Configuration related to coverage reporting.
    """

    disconnect_providers_after: bool = True
    """
    Set to ``False`` to keep providers connected at the end of the test run.
    """

    hd_path: str = DEFAULT_HD_PATH
    """
    The hd_path to use when generating the test accounts.
    """

    provider: EthTesterProviderConfig = EthTesterProviderConfig()
    """
    Settings for the provider.
    """


@plugins.register(plugins.Config)
def config_class():
    return Config


@plugins.register(plugins.AccountPlugin)
def account_types():
    return TestAccountContainer, TestAccount


@plugins.register(plugins.ProviderPlugin)
def providers():
    yield "ethereum", LOCAL_NETWORK_NAME, LocalProvider
