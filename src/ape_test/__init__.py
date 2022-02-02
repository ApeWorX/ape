from ape import plugins
from ape.api import ConfigItem
from ape.api.networks import LOCAL_NETWORK_NAME

from .accounts import TestAccount, TestAccountContainer
from .providers import LocalProvider


class Config(ConfigItem):
    mnemonic: str = "test test test test test test test test test test test junk"
    number_of_accounts: int = 10


@plugins.register(plugins.Config)
def config_class():
    return Config


@plugins.register(plugins.AccountPlugin)
def account_types():
    return TestAccountContainer, TestAccount


@plugins.register(plugins.ProviderPlugin)
def providers():
    yield "ethereum", LOCAL_NETWORK_NAME, LocalProvider
