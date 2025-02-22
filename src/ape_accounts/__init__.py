from importlib import import_module

from ape.plugins import AccountPlugin, register


@register(AccountPlugin)
def account_types():
    from ape_accounts.accounts import AccountContainer, KeyfileAccount

    return AccountContainer, KeyfileAccount


def __getattr__(name: str):
    return getattr(import_module("ape_accounts.accounts"), name)


__all__ = [
    "AccountContainer",
    "KeyfileAccount",
    "generate_account",
    "import_account_from_mnemonic",
    "import_account_from_private_key",
]
