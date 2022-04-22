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


@cli.command(short_help="Initialize a new cache db")
def init():
    models.Base.metadata.create_all(bind=get_engine().engine)


@cli.command(short_help="Call and print SQL Statement to the cache db")
@click.argument("sql")
def query(sql):
    with get_engine().engine.connect() as conn:
        click.echo(pd.DataFrame(conn.execute(sql)))


@cli.command(short_help="Purges entire database")
def purge():
    db_file = get_engine().database_file
    db_file.unlink()
