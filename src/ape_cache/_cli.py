import click
import pandas as pd

from ape import networks
from ape.cli import NetworkBoundCommand, network_option
from ape.logging import logger
from ape.utils import ManagerAccessMixin


def get_engine():
    return ManagerAccessMixin.query_manager.engines["cache"]


@click.group(short_help="Query from caching database")
def cli():
    """
    Manage query caching database (beta).
    """


@cli.command(short_help="Initialize a new cache database")
@network_option(required=True)
def init(network):
    """
    Initializes an SQLite database and creates a file to store data
    from the provider.

    Note that ape cannot store local data in this database. You have to
    give an ecosystem name and a network name to initialize the database.
    """

    provider = networks.get_provider_from_choice(network)
    ecosystem_name = provider.network.ecosystem.name
    network_name = provider.network.name

    get_engine().init_database(ecosystem_name, network_name)
    logger.success(f"Caching database initialized for {ecosystem_name}:{network_name}.")


@cli.command(
    cls=NetworkBoundCommand,
    short_help="Call and print SQL statement to the cache database",
)
@network_option()
@click.argument("query_str")
def query(query_str, network):
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
            click.echo(pd.DataFrame(results))


@cli.command(short_help="Purges entire database")
@network_option(required=True)
def purge(network):
    """
    Purges data from the selected database instance.

    Note that this is a destructive purge, and will remove the database file from disk.
    If you want to store data in the caching system, you will have to
    re-initiate the database following a purge.

    Note that an ecosystem name and network name are required to
    purge the database of choice.
    """

    provider = networks.get_provider_from_choice(network)
    ecosystem_name = provider.network.ecosystem.name
    network_name = provider.network.name

    get_engine().purge_database(ecosystem_name, network_name)
    logger.success(f"Caching database purged for {ecosystem_name}:{network_name}.")
