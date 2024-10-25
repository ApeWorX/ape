import json
from collections.abc import Callable
from importlib import import_module
from typing import TYPE_CHECKING

import click
import yaml
from rich import print as echo_rich_text
from rich.tree import Tree

from ape.cli.choices import OutputFormat
from ape.cli.options import ape_cli_context, network_option, output_format_option
from ape.exceptions import NetworkError
from ape.logging import LogLevel
from ape.types.basic import _LazySequence
from ape.utils.basemodel import ManagerAccessMixin as access

if TYPE_CHECKING:
    from ape.api.providers import SubprocessProvider


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
        yield from getattr(access.network_manager, f"{name}_names")

    return _LazySequence(gen)


@cli.command(name="list", short_help="List registered networks")
@ape_cli_context()
@output_format_option()
@_filter_option("ecosystem", _lazy_get("ecosystem"))
@_filter_option("network", _lazy_get("network"))
@_filter_option("provider", _lazy_get("provider"))
def _list(cli_ctx, output_format, ecosystem_filter, network_filter, provider_filter):
    """
    List all the registered ecosystems, networks, and providers.
    """
    network_data = cli_ctx.network_manager.get_network_data(
        ecosystem_filter=ecosystem_filter,
        network_filter=network_filter,
        provider_filter=provider_filter,
    )

    if output_format == OutputFormat.TREE:
        default_suffix = "[dim default]  (default)"
        ecosystems = network_data["ecosystems"]
        ecosystems = sorted(ecosystems, key=lambda e: e["name"])

        def make_sub_tree(data: dict, create_tree: Callable) -> Tree:
            name = f"[bold green]{data['name']}"
            if "isDefault" in data and data["isDefault"]:
                name += default_suffix

            sub_tree = create_tree(name)
            return sub_tree

        for ecosystem in ecosystems:
            ecosystem_tree = make_sub_tree(ecosystem, Tree)
            _networks = {n["name"]: n for n in ecosystem["networks"]}
            _networks = {n: _networks[n] for n in sorted(_networks)}
            for network_name, network in _networks.items():
                providers = network["providers"]
                if providers:
                    network_tree = make_sub_tree(network, ecosystem_tree.add)
                    providers = sorted(providers, key=lambda p: p["name"])
                    for provider in providers:
                        make_sub_tree(provider, network_tree.add)

            if _networks and ecosystem_tree.children:
                echo_rich_text(ecosystem_tree)

    elif output_format == OutputFormat.YAML:
        if not isinstance(network_data, dict):
            raise TypeError(
                f"Unexpected network data type: {type(network_data)}. "
                f"Expecting dict. YAML dump will fail."
            )

        try:
            click.echo(yaml.dump(network_data, sort_keys=True).strip())
        except ValueError as err:
            try:
                data_str = json.dumps(network_data)
            except Exception:
                data_str = str(network_data)

            raise NetworkError(
                f"Network data did not dump to YAML: {data_str}\nActual err: {err}"
            ) from err


@cli.command(short_help="Start a node process")
@ape_cli_context()
@network_option(default="ethereum:local:node")
def run(cli_ctx, provider):
    """
    Start a subprocess node as if running independently
    and stream stdout and stderr.
    """
    # Ignore extra loggers, such as web3 loggers.
    cli_ctx.logger._extra_loggers = {}
    providers_module = import_module("ape.api.providers")
    if not isinstance(provider, providers_module.SubprocessProvider):
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


def _run(cli_ctx, provider: "SubprocessProvider"):
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
