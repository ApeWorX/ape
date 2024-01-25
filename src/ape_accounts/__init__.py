from ape import plugins

from .accounts import AccountContainer, KeyfileAccount, generate_account


@plugins.register(plugins.AccountPlugin)
def account_types():
    return AccountContainer, KeyfileAccount


__all__ = ["AccountContainer", "KeyfileAccount", "generate_account"]
