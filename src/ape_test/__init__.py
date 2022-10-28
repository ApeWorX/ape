from typing import List, Optional

from pydantic import PositiveInt

from ape import plugins
from ape.api import PluginConfig
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.utils import DEFAULT_NUMBER_OF_TEST_ACCOUNTS, DEFAULT_TEST_MNEMONIC

from .accounts import TestAccount, TestAccountContainer
from .provider import LocalProvider


class GasExclusion(PluginConfig):
    contract: str = "*"  # If only given method, searches across all contracts.
    method: Optional[str] = None


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
    Contract methods patterns to skip. Specify ``contract:`` and not
    ``method:`` to skip all methods in the contract. Only specify
    ``method:`` to skip all methods across all contracts. Specify
    both to skip methods in a certain contracts. Entries use glob-rules;
    use ``prefix_*`` to skip all items with a certain prefix.
    """


class Config(PluginConfig):
    mnemonic: str = DEFAULT_TEST_MNEMONIC
    number_of_accounts: PositiveInt = DEFAULT_NUMBER_OF_TEST_ACCOUNTS
    gas: GasConfig = GasConfig()


@plugins.register(plugins.Config)
def config_class():
    return Config


@plugins.register(plugins.AccountPlugin)
def account_types():
    return TestAccountContainer, TestAccount


@plugins.register(plugins.ProviderPlugin)
def providers():
    yield "ethereum", LOCAL_NETWORK_NAME, LocalProvider
