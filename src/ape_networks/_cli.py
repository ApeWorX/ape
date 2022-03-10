from typing import Callable, Dict

import click
from rich import print as echo_rich_text
from rich.tree import Tree

from ape.cli import ape_cli_context
from ape.cli.choices import OutputFormat
from ape.cli.options import output_format_option


@click.group(short_help="Manage networks")
def cli():
    """
    Command-line helper for managing networks.
    """


@cli.command(name="list", short_help="List registered networks")
@ape_cli_context()
@output_format_option()
@click.option(
    "--ecosystem", "ecosystem_filter", multiple=Tree, help="Filter the results by ecosystem"
)
@click.option("--network", "network_filter", multiple=Tree, help="Filter the results by ecosystem")
@click.option("--provider", "provider_filter", multiple=Tree, help="Filter the results by provider")
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
            for network in _networks:
                if network_filter and network["name"] not in network_filter:
                    continue

                providers = network["providers"]
                if providers:
                    network_tree = make_sub_tree(network, ecosystem_tree.add)
                    for provider in providers:
                        if provider_filter and provider["name"] not in provider_filter:
                            continue

                        make_sub_tree(provider, network_tree.add)

            if _networks:
                echo_rich_text(ecosystem_tree)
    elif output_format == OutputFormat.YAML:
        click.echo(cli_ctx.network_manager.networks_yaml.strip())
