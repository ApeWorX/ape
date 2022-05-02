import click
import pandas as pd

from ape.cli import NetworkBoundCommand, network_option
from ape.utils import ManagerAccessMixin


def get_engine():
    return ManagerAccessMixin.query_manager.engines["cache"]


@click.group(short_help="Query from caching database")
def cli():
    """
    Command-line helper for managing query caching database.
    """


@cli.command(
    cls=NetworkBoundCommand,
    short_help="Initialize a new cache database"
)
@network_option()
def init(network):
    get_engine().init_db()
    click.echo("Caching database initialized.")


@cli.command(
    cls=NetworkBoundCommand,
    short_help="Call and print SQL statement to the cache database"
)
@network_option()
@click.argument("sql")
def query(sql, network):
    with get_engine().engine.connect() as conn:
        click.echo(pd.DataFrame(conn.execute(sql)))


@cli.command(cls=NetworkBoundCommand, short_help="Purges entire database")
@network_option()
def purge(network):
    get_engine().purge_db()
    click.echo("Caching database purged.")
