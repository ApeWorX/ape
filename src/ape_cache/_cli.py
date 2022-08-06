import click
import pandas as pd
from sqlalchemy import create_engine  # type: ignore

from ape.cli import NetworkBoundCommand, network_option
from ape.logging import logger
from ape.utils import ManagerAccessMixin


def get_engine():
    return ManagerAccessMixin.query_manager.engines["cache"]


@click.group(short_help="Query from caching database")
def cli():
    """
    Command-line helper for managing query caching database.
    """


@cli.command(cls=NetworkBoundCommand, short_help="Initialize a new cache database")
@network_option()
def init(network):
    get_engine().init_db()
    logger.info("Caching database initialized.")


@cli.command(
    cls=NetworkBoundCommand, short_help="Call and print SQL statement to the cache database"
)
@network_option()
@click.argument("sql")
def query(sql, network):
    if get_engine().database_file.is_file():
        with create_engine(get_engine().sqlite_db, pool_pre_ping=True).connect() as conn:
            click.echo(pd.DataFrame(conn.execute(sql)))

    else:
        click.echo("Database not initialized")


@cli.command(cls=NetworkBoundCommand, short_help="Purges entire database")
@network_option()
def purge(network):
    get_engine().purge_db()
    logger.info("Caching database purged.")
