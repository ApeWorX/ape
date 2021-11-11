import click

from ape import networks
from ape.cli import ape_cli_context


@click.group(short_help="Manage networks")
def cli():
    """
    Command-line helper for managing networks.
    """


@cli.command(name="list", short_help="List registered networks")
@ape_cli_context()
def _list(cli_ctx):
    click.echo(networks.networks_yaml)
