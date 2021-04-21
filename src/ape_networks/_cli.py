import click

from ape import networks


@click.group(short_help="Manage networks")
def cli():
    """
    Command-line helper for managing networks.
    """


@cli.command(name="list", short_help="List registered networks")
def _list():
    click.echo("ecosystems:")
    default_ecosystem = networks.default_ecosystem.name
    for ecosystem_name in networks:
        if ecosystem_name == default_ecosystem:
            click.echo(f"- name: {ecosystem_name}  # Default")
        else:
            click.echo(f"- name: {ecosystem_name}")

        ecosystem = networks[ecosystem_name]

        default_network = ecosystem.default_network
        for network_name in getattr(networks, ecosystem_name):

            if network_name == default_network:
                click.echo(f"  - name: {network_name}  # Default")
            else:
                click.echo(f"  - name: {network_name}")

            network = ecosystem[network_name]

            if network.explorer:
                click.echo(f"    explorer: {network.explorer.name}")

            click.echo("    providers:")

            default_provider = network.default_provider
            for provider_name in network.providers:
                if provider_name == default_provider:
                    click.echo(f"    - {provider_name}  # Default")
                else:
                    click.echo(f"    - {provider_name}")
