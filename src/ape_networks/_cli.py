import click

from ape import networks

_PREFIX_SPACING = "    "


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


def _echo_ecosystem(name):
    _echo_output(name, networks.default_ecosystem.name)
    ecosystem = networks[name]

    for network_name in getattr(networks, name):
        _echo_network(ecosystem, network_name)


def _echo_network(ecosystem, name):
    _echo_output(name, ecosystem.default_network)
    network = ecosystem[name]

    if network.explorer:
        click.echo(f"{_PREFIX_SPACING}explorer: {network.explorer.name}")

    click.echo(f"{_PREFIX_SPACING}providers:")

    for provider_name in network.providers:
        _echo_output(provider_name, network.default_provider)


def _echo_output(name, default_name):
    output = _create_output_line(name)
    if name == default_name:
        output = f"{output}  # Default"

    click.echo(output)


def _create_output_line(output):
    return f"{_PREFIX_SPACING}- {output}"
