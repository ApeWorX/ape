from ape import plugins

from ._cli import cli


@plugins.register(plugins.CliPlugin)
def cli_subcommand():
    return cli
