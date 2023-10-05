from typing import Callable, Dict

import click
from rich import print as echo_rich_text
from rich.tree import Tree

from ape import networks
from ape.api import SubprocessProvider
from ape.cli import ape_cli_context, network_option
from ape.cli.choices import OutputFormat
from ape.cli.options import output_format_option
from ape.logging import LogLevel
from ape.types import _LazySequence


def _filter_option(name: str, options):
    return click.option(
        f"--{name}",
        f"{name}_filter",
        multiple=True,
        help=f"Filter the results by {name}",
        type=click.Choice(options),
    )


@click.group(short_help="Manage networks")
def cli():
    """
    Command-line helper for managing networks.
    """


def _lazy_get(name: str) -> _LazySequence:
    # NOTE: Using fn generator to maintain laziness.
    def gen():
        yield from getattr(networks, f"{name}_names")

    return _LazySequence(gen)


@cli.command(name="list", short_help="List registered networks")
@ape_cli_context()
@output_format_option()
@_filter_option("ecosystem", _lazy_get("ecosystem"))
@_filter_option("network", _lazy_get("network"))
@_filter_option("provider", _lazy_get("provider"))
def _list(cli_ctx, output_format, ecosystem_filter, network_filter, provider_filter):
    if output_format == OutputFormat.TREE:
        default_suffix = "[dim default]  (default)"
        ecosystems = {e["name"]: e for e in cli_ctx.network_manager.network_data["ecosystems"]}
        ecosystems = {n: ecosystems[n] for n in sorted(ecosystems)}

        def make_sub_tree(data: Dict, create_tree: Callable) -> Tree:
            name = f"[bold green]{data['name']}"
            if "isDefault" in data and data["isDefault"]:
                name += default_suffix

            sub_tree = create_tree(name)
            return sub_tree

        for ecosystem_name, ecosystem in ecosystems.items():
            if ecosystem_filter and ecosystem["name"] not in ecosystem_filter:
                continue

            ecosystem_tree = make_sub_tree(ecosystem, Tree)
            _networks = {n["name"]: n for n in ecosystem["networks"]}
            _networks = {n: _networks[n] for n in sorted(_networks)}
            if network_filter:
                _networks = {n: v for n, v in _networks.items() if n in network_filter}

            for network_name, network in _networks.items():
                if network_filter and network_name not in network_filter:
                    continue

                providers = network["providers"]
                if provider_filter:
                    providers = [p for p in providers if p["name"] in provider_filter]

                if providers:
                    network_tree = make_sub_tree(network, ecosystem_tree.add)
                    providers = sorted(providers, key=lambda p: p["name"])
                    for provider in providers:
                        make_sub_tree(provider, network_tree.add)

            if _networks and ecosystem_tree.children:
                echo_rich_text(ecosystem_tree)

    elif output_format == OutputFormat.YAML:
        click.echo(cli_ctx.network_manager.networks_yaml.strip())


@cli.command()
@ape_cli_context()
@network_option(default="ethereum:local:geth")
def run(cli_ctx, network):
    """
    Start a node process
    """

    # Ignore extra loggers, such as web3 loggers.
    cli_ctx.logger._extra_loggers = {}

    network_ctx = cli_ctx.network_manager.parse_network_choice(network)
    provider = network_ctx._provider
    if not isinstance(provider, SubprocessProvider):
        cli_ctx.abort(
            f"`ape networks run` requires a provider that manages a process, not '{provider.name}'."
        )
    elif provider.is_connected:
        cli_ctx.abort("Process already running.")

    # Start showing process logs.
    original_level = cli_ctx.logger.level
    original_format = cli_ctx.logger.fmt
    cli_ctx.logger.set_level(LogLevel.DEBUG)

    # Change format to exclude log level (since it is always just DEBUG)
    cli_ctx.logger.format(fmt="%(message)s")
    try:
        _run(cli_ctx, provider)
    finally:
        cli_ctx.logger.set_level(original_level)
        cli_ctx.logger.format(fmt=original_format)


def _run(cli_ctx, provider: SubprocessProvider):
    provider.connect()
    if process := provider.process:
        try:
            process.wait()
        finally:
            try:
                provider.disconnect()
            except Exception:
                # Prevent not being able to CTRL-C.
                cli_ctx.abort("Terminated")

    else:
        provider.disconnect()
        cli_ctx.abort("Process already running.")
