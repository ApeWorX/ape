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
    Create the file cache directory for a network.

    Ape cannot store local chain data here. Pass an ecosystem and a network.
    """

    folder = get_engine().cache_folder(ecosystem.name, network.name)
    folder.mkdir(parents=True, exist_ok=True)
    logger.success(f"Query cache ready for {ecosystem.name}:{network.name}.")


@cli.command(
    cls=ConnectedProviderCommand,
    short_help="Call and print SQL statement to the cache database",
)
@click.argument("query_str")
def query(query_str):
    """
    SQL queries against the old cache database are no longer supported.

    Read cached chain data with ``.query`` in Python instead.
    """

    raise click.ClickException(
        f"SQL cache queries were removed, so {query_str!r} was not run. "
        "Use `.query` in Python to read chain data."
    )


@cli.command(short_help="Purges entire database")
@ape_cli_context()
@network_option(required=True)
def purge(cli_ctx, ecosystem, network):
    """
    Delete the file cache for a network.

    This removes cached query data from disk. Chain data outside the query
    cache is left in place.
    """

    get_engine().prune_database(ecosystem.name, network.name)
    logger.success(f"Query cache purged for {ecosystem.name}:{network.name}.")
