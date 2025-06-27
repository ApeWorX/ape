from importlib import import_module
from typing import TYPE_CHECKING

import click

from ape.cli import ape_cli_context
from ape.cli.commands import ConnectedProviderCommand
from ape.cli.options import network_option
from ape.logging import logger

if TYPE_CHECKING:
    from ape_cache.query import CacheQueryProvider


def get_engine() -> "CacheQueryProvider":
    from ape.utils.basemodel import ManagerAccessMixin

    return ManagerAccessMixin.query_manager.engines["cache"]


@click.group(short_help="Query from caching database")
def cli():
    """
    Manage query caching database (beta).
    """


@cli.command(short_help="Initialize a new cache database")
@ape_cli_context()
@network_option(required=True)
def init(cli_ctx, ecosystem, network):
    """
    Initializes an SQLite database and creates a file to store data
    from the provider.

    Note that ape cannot store local data in this database. You have to
    give an ecosystem name and a network name to initialize the database.
    """

    get_engine().init_database(ecosystem.name, network.name)
    logger.success(f"Caching database initialized for {ecosystem.name}:{network.name}.")


@cli.command(
    cls=ConnectedProviderCommand,
    short_help="Call and print SQL statement to the cache database",
)
@click.argument("query_str")
def query(query_str):
    """
    Allows for a query of the database from an SQL statement.

    Note that without an SQL statement, this method will not return
    any data from the caching database.

    Also note that an ecosystem name and a network name are required
    to make the correct connection to the database.
    """

    with get_engine().database_connection as conn:
        results = conn.execute(query_str).fetchall()
        if results:
            pd = import_module("pandas")
            click.echo(pd.DataFrame(results))


@cli.command(short_help="Purges entire database")
@ape_cli_context()
@network_option(required=True)
def purge(cli_ctx, ecosystem, network):
    """
    Purges data from the selected database instance.

    Note that this is a destructive purge, and will remove the database file from disk.
    If you want to store data in the caching system, you will have to
    re-initiate the database following a purge.

    Note that an ecosystem name and network name are required to
    purge the database of choice.
    """

    get_engine().purge_database(ecosystem.name, network.name)
    logger.success(f"Caching database purged for {ecosystem.name}:{network.name}.")
