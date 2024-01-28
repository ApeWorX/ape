from ape import plugins

from .accounts import (
    AccountContainer,
    KeyfileAccount,
    generate_account,
    import_account_from_mnemonic,
    import_account_from_private_key,
)


@plugins.register(plugins.AccountPlugin)
def account_types():
    return AccountContainer, KeyfileAccount


__all__ = [
    "AccountContainer",
    "KeyfileAccount",
    "generate_account",
    "import_account_from_mnemonic",
    "import_account_from_private_key",
]
