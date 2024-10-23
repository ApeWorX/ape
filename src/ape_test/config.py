from typing import NewType, Optional, Union

from pydantic import NonNegativeInt, field_validator

from ape.api.config import PluginConfig
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.testing import (
    DEFAULT_NUMBER_OF_TEST_ACCOUNTS,
    DEFAULT_TEST_ACCOUNT_BALANCE,
    DEFAULT_TEST_CHAIN_ID,
    DEFAULT_TEST_HD_PATH,
    DEFAULT_TEST_MNEMONIC,
)


class EthTesterProviderConfig(PluginConfig):
    chain_id: int = DEFAULT_TEST_CHAIN_ID
    auto_mine: bool = True


class GasExclusion(PluginConfig):
    contract_name: str = "*"  # If only given method, searches across all contracts.
    method_name: Optional[str] = None  # By default, match all methods in a contract


CoverageExclusion = NewType("CoverageExclusion", GasExclusion)


class GasConfig(PluginConfig):
    """
    Configuration related to test gas reports.
    """

    exclude: list[GasExclusion] = []
    """
    Contract methods patterns to skip. Specify ``contract_name:`` and not
    ``method_name:`` to skip all methods in the contract. Only specify
    ``method_name:`` to skip all methods across all contracts. Specify
    both to skip methods in a certain contracts. Entries use glob-rules;
    use ``prefix_*`` to skip all items with a certain prefix.
    """

    reports: list[str] = []
    """
    Report-types to use. Currently, only supports `terminal`.
    """

    @field_validator("reports", mode="before")
    @classmethod
    def validate_reports(cls, values):
        values = list(set(values or []))
        valid = ("terminal",)
        for val in values:
            if val not in valid:
                valid_str = ", ".join(valid)
                raise ValueError(f"Invalid gas-report format '{val}'. Valid: {valid_str}")

        return values

    @property
    def show(self) -> bool:
        return "terminal" in self.reports


_ReportType = Union[bool, dict]
"""Dict is for extra report settings."""


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

    exclude: list[CoverageExclusion] = []
    """
    Contract methods patterns to skip. Specify ``contract_name:`` and not
    ``method_name:`` to skip all methods in the contract. Only specify
    ``method_name:`` to skip all methods across all contracts. Specify
    both to skip methods in a certain contracts. Entries use glob-rules;
    use ``prefix_*`` to skip all items with a certain prefix.
    """


class ApeTestConfig(PluginConfig):
    balance: int = DEFAULT_TEST_ACCOUNT_BALANCE
    """
    The starting-balance of every test account in Wei (NOT Ether).
    """

    coverage: CoverageConfig = CoverageConfig()
    """
    Configuration related to coverage reporting.
    """

    disconnect_providers_after: bool = True
    """
    Set to ``False`` to keep providers connected at the end of the test run.
    """

    gas: GasConfig = GasConfig()
    """
    Configuration related to gas reporting.
    """

    hd_path: str = DEFAULT_TEST_HD_PATH
    """
    The hd_path to use when generating the test accounts.
    """

    mnemonic: str = DEFAULT_TEST_MNEMONIC
    """
    The mnemonic to use when generating the test accounts.
    """

    number_of_accounts: NonNegativeInt = DEFAULT_NUMBER_OF_TEST_ACCOUNTS
    """
    The number of test accounts to generate in the provider.
    """

    provider: EthTesterProviderConfig = EthTesterProviderConfig()
    """
    Settings for the provider.
    """

    @field_validator("balance", mode="before")
    @classmethod
    def validate_balance(cls, value):
        return (
            value
            if isinstance(value, int)
            else ManagerAccessMixin.conversion_manager.convert(value, int)
        )
