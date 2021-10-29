from ape import plugins

from .accounts import TestAccount, TestAccountContainer
from .providers import LocalNetwork


@plugins.register(plugins.ProviderPlugin)
def providers():
    yield "ethereum", "development", LocalNetwork


@plugins.register(plugins.AccountPlugin)
def account_types():
    return TestAccountContainer, TestAccount
