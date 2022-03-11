from typing import Callable, Dict

import click
from rich import print as echo_rich_text
from rich.tree import Tree

from ape import networks
from ape.cli import ape_cli_context
from ape.cli.choices import OutputFormat
from ape.cli.options import output_format_option


def _filter_option(name: str, options):
    return click.option(
        f"--{name}",
        f"{name}_filter",
        multiple=Tree,
        help=f"Filter the results by {name}",
        type=click.Choice(options),
    )


@click.group(short_help="Manage networks")
def cli():
    """
    Command-line helper for managing networks.
    """


@cli.command(name="list", short_help="List registered networks")
@ape_cli_context()
@output_format_option()
@_filter_option("ecosystem", networks.ecosystem_names)
@_filter_option("network", networks.network_names)
@_filter_option("provider", networks.provider_names)
def _list(cli_ctx, output_format, ecosystem_filter, network_filter, provider_filter):
    if output_format == OutputFormat.TREE:
        default_suffix = "[dim default]  (default)"
        ecosystems = cli_ctx.network_manager.network_data["ecosystems"]

        def make_sub_tree(data: Dict, create_tree: Callable) -> Tree:
            name = f"[bold green]{data['name']:}"
            if "isDefault" in data and data["isDefault"]:
                name += default_suffix

            sub_tree = create_tree(name)
            return sub_tree

        for ecosystem in ecosystems:
            if ecosystem_filter and ecosystem["name"] not in ecosystem_filter:
                continue

            ecosystem_tree = make_sub_tree(ecosystem, Tree)
            _networks = ecosystem["networks"]
            if network_filter:
                _networks = [n for n in _networks if n["name"] in network_filter]

            for network in _networks:
                if network_filter and network["name"] not in network_filter:
                    continue

                providers = network["providers"]
                if provider_filter:
                    providers = [p for p in providers if p["name"] in provider_filter]

                if providers:
                    network_tree = make_sub_tree(network, ecosystem_tree.add)
                    for provider in providers:
                        make_sub_tree(provider, network_tree.add)

            if _networks and ecosystem_tree.children:
                echo_rich_text(ecosystem_tree)

    elif output_format == OutputFormat.YAML:
        click.echo(cli_ctx.network_manager.networks_yaml.strip())
