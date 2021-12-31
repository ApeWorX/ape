from typing import Callable, Dict

import click
from rich import print as echo_rich_text
from rich.tree import Tree

from ape import networks
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
def _list(cli_ctx, output_format):
    if output_format == OutputFormat.TREE:
        default_suffix = "[dim default]  (default)"
        ecosystems = networks.network_data["ecosystems"]

        def make_sub_tree(data: Dict, create_tree: Callable) -> Tree:
            name = f"[bold green]{data['name']:}"
            if "isDefault" in data and data["isDefault"]:
                name += default_suffix

            sub_tree = create_tree(name)
            return sub_tree

        for ecosystem in ecosystems:
            ecosystem_tree = make_sub_tree(ecosystem, Tree)
            _networks = ecosystem["networks"]
            for network in _networks:
                providers = network["providers"]
                if providers:
                    network_tree = make_sub_tree(network, ecosystem_tree.add)
                    for provider in providers:
                        make_sub_tree(provider, network_tree.add)

            if _networks:
                echo_rich_text(ecosystem_tree)
    elif output_format == OutputFormat.YAML:
        click.echo(networks.networks_yaml.strip())
