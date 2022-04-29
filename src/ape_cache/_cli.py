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
    db_file = get_engine().database_file
    if not db_file.is_file():
        click.echo("initializing database")
        models.Base.metadata.create_all(bind=get_engine().engine)
        return click.echo("caching database initialized")
    click.echo("caching database already exists!")


# TODO: add migrate command


@cli.command(short_help="Call and print SQL Statement to the cache db")
@click.argument("sql")
def query(sql):
    with get_engine().engine.connect() as conn:
        click.echo(pd.DataFrame(conn.execute(sql)))


@cli.command(short_help="Purges entire database")
def purge():
    db_file = get_engine().database_file
    if not db_file.is_file():
        # Add check here to show we have a file that exists
        return click.echo("caching database must be initialized with `ape cache init`")
    db_file.unlink()
    click.echo("caching database purged")
