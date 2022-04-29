import click
import pandas as pd

from ape.utils import ManagerAccessMixin

from . import models


def get_engine():
    return ManagerAccessMixin.query_manager.engines["cache"]


@click.group(short_help="Query from caching database")
def cli():
    """
    Command-line helper for managing query caching database.
    """


@cli.command(short_help="Initialize a new cache database")
def init():
    get_engine().init_db()
    click.echo("Caching database initialized.")


@cli.command(short_help="Call and print SQL statement to the cache database")
@click.argument("sql")
def query(sql):
    with get_engine().engine.connect() as conn:
        click.echo(pd.DataFrame(conn.execute(sql)))


@cli.command(short_help="Purges entire database")
def purge():
    get_engine().purge_db()
    click.echo("Caching database purged.")
