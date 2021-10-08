import click

from ape import networks


@click.group(short_help="Manage networks")
def cli():
    """
    Command-line helper for managing networks.
    """


@cli.command(name="list", short_help="List registered networks")
def _list():
    click.echo(networks.networks_yaml)
