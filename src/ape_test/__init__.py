from ape import plugins

from .accounts import TestAccount, TestAccountContainer


@plugins.register(plugins.AccountPlugin)
def account_types():
    return TestAccountContainer, TestAccount
