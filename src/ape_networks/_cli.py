from typing import Optional

import click

from ape import networks
from ape.api import EcosystemAPI

_SPACED_TAB = "  "


@click.group(short_help="Manage networks")
def cli():
    """
    Command-line helper for managing networks.
    """


@cli.command(name="list", short_help="List registered networks")
def _list():
    click.echo("ecosystems:")
    for ecosystem_name in networks:
        _echo_ecosystem(ecosystem_name)


def _echo_ecosystem(name: str):
    _output_line(name, default_value=networks.default_ecosystem.name)
    ecosystem = networks[name]

    for network_name in getattr(networks, name):
        _echo_network(ecosystem, network_name)


def _echo_network(ecosystem: EcosystemAPI, name: str):
    _output_line(name, num_of_tabs=1, default_value=ecosystem.default_network)
    network = ecosystem[name]

    if network.explorer:
        click.echo(f"{_SPACED_TAB * 2}explorer: {network.explorer.name}")

    click.echo(f"{_SPACED_TAB * 2}providers:")

    for provider_name in network.providers:
        _output_line(provider_name, num_of_tabs=2, default_value=network.default_provider, key=None)


def _output_line(
    value: str, num_of_tabs: int = 0, default_value: str = None, key: Optional[str] = "name"
):
    key = f"{key}: " if key else ""
    comment = "  # Default" if value == default_value else ""
    output = f"{_SPACED_TAB * num_of_tabs}- {key}{value}{comment}"
    click.echo(output)
