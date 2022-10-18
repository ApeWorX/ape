from pydantic import PositiveInt

from ape import plugins
from ape.api import PluginConfig
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.utils import DEFAULT_NUMBER_OF_TEST_ACCOUNTS, DEFAULT_TEST_MNEMONIC

from .accounts import TestAccount, TestAccountContainer
from .provider import LocalProvider


class Config(PluginConfig):
    mnemonic: str = DEFAULT_TEST_MNEMONIC
    number_of_accounts: PositiveInt = DEFAULT_NUMBER_OF_TEST_ACCOUNTS


@plugins.register(plugins.Config)
def config_class():
    return Config


@plugins.register(plugins.AccountPlugin)
def account_types():
    return TestAccountContainer, TestAccount


@plugins.register(plugins.ProviderPlugin)
def providers():
    yield "ethereum", LOCAL_NETWORK_NAME, LocalProvider
