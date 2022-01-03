from ape import plugins

from .accounts import AccountContainer, KeyfileAccount


@plugins.register(plugins.AccountPlugin)
def account_types():
    return AccountContainer, KeyfileAccount
