from ape import plugins

from ._cli import cli


@plugins.register(plugins.CliPlugin)
def register_cli():
    return cli
