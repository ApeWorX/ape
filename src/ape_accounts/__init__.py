from ape import plugins

from ._cli import cli
from .accounts import AccountContainer


@plugins.register(plugins.CliPlugin)
def register_cli():
    return cli


@plugins.register(plugins.AccountPlugin)
def register_accounts():
    return AccountContainer
