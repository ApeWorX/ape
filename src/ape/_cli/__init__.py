import click
from ape_compile._cli import cli as compile
from ape_console._cli import cli as console
from ape_networks._cli import cli as networks
from ape_plugins._cli import cli as plugins

from ape._cli.groups import ApeCLI
from ape._cli.options import shared_options
from ape_accounts._cli import cli as accounts  # type: ignore

CONTEXT_SETTINGS = {
    "help_option_names": ["-h", "--help"],
    "max_content_width": 200,
}


@click.group(
    cls=ApeCLI,
    context_settings=CONTEXT_SETTINGS,
    invoke_without_command=True,
    no_args_is_help=True,
)
@shared_options()
def cli():
    pass


cli.add_command(accounts)
cli.add_command(compile)
cli.add_command(console)
cli.add_command(plugins)
cli.add_command(networks)
