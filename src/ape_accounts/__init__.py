from ape import plugins

from ._cli import cli
from .accounts import AccountContainer


@plugins.register(plugins.CliPlugin)
def cli_subcommand():
    return cli


@plugins.register(plugins.AccountPlugin)
def accounts_container():
    return AccountContainer
