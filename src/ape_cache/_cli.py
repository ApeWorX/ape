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
    Command-line helper for managing query caching database.
    """


@cli.command(short_help="Initialize a new cache database")
@network_option()
def init(network):
    provider = networks.get_provider_from_choice(network)
    ecosystem_name = provider.network.ecosystem.name
    network_name = provider.network.name

    get_engine().init_database(ecosystem_name, network_name)
    logger.info(f"Caching database initialized for {ecosystem_name}:{network_name}.")


@cli.command(
    cls=NetworkBoundCommand,
    short_help="Call and print SQL statement to the cache database",
)
@network_option()
@click.argument("sql")
def query(sql, network):
    with get_engine().database_connection as conn:
        results = conn.execute(sql).fetchall()
        if results:
            click.echo(pd.DataFrame(results))


@cli.command(short_help="Purges entire database")
@network_option()
def purge(network):
    provider = networks.get_provider_from_choice(network)
    ecosystem_name = provider.network.ecosystem.name
    network_name = provider.network.name

    get_engine().purge_database(ecosystem_name, network_name)
    logger.info(f"Caching database purged for {ecosystem_name}:{network_name}.")
