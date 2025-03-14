import json
from collections.abc import Callable, Sequence
from typing import TYPE_CHECKING

import click
import yaml
from rich import print as echo_rich_text
from rich.tree import Tree

from ape.cli.choices import LazyChoice, OutputFormat
from ape.cli.options import ape_cli_context, network_option, output_format_option
from ape.exceptions import NetworkError
from ape.logging import LogLevel

if TYPE_CHECKING:
    from ape.api.providers import SubprocessProvider


def _filter_option(name: str, get_options: Callable[[], Sequence[str]]):
    return click.option(
        f"--{name}",
        f"{name}_filter",
        multiple=True,
        help=f"Filter the results by {name}",
        type=LazyChoice(get_options),
    )


@click.group(short_help="Manage networks")
def cli():
    """
    Command-line helper for managing networks.
    """


def _lazy_get(name: str) -> Sequence:
    # NOTE: Using fn generator to maintain laziness.
    def gen():
        from ape.utils.basemodel import ManagerAccessMixin as access

        yield from getattr(access.network_manager, f"{name}_names")

    from ape.types.basic import _LazySequence

    return _LazySequence(gen)


@cli.command(name="list", short_help="List registered networks")
@ape_cli_context()
@output_format_option()
@_filter_option("ecosystem", lambda: _lazy_get("ecosystem"))
@_filter_option("network", lambda: _lazy_get("network"))
@_filter_option("provider", lambda: _lazy_get("provider"))
@click.option("--running", is_flag=True, help="List running networks")
def _list(cli_ctx, output_format, ecosystem_filter, network_filter, provider_filter, running):
    """
    List all the registered ecosystems, networks, and providers.
    """
    if running:
        # TODO: Honor filter args.
        _print_running_networks(cli_ctx)
        return

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
            if data.get("isDefault"):
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
            click.echo(yaml.safe_dump(network_data, sort_keys=True).strip())
        except ValueError as err:
            try:
                data_str = json.dumps(network_data)
            except Exception:
                data_str = str(network_data)

            raise NetworkError(
                f"Network data did not dump to YAML: {data_str}\nActual err: {err}"
            ) from err


def _print_running_networks(cli_ctx):
    from ape.utils.os import clean_path

    rows = [["PID", "NETWORK", "IPC", "HTTP", "WS"]]  # Store headers as a list
    for pid, node in cli_ctx.network_manager.running_nodes.nodes.items():
        rows.append(
            [
                pid,
                node.network_choice,
                str(clean_path(node.ipc_path) if node.ipc_path else None),
                node.http_uri,
                node.ws_uri,
            ]
        )

    if len(rows) == 1:
        # Only header row.
        click.echo("Local node(s) not running.")

    else:
        col_widths = [max(len(str(row[i])) for row in rows) for i in range(len(rows[0]))]
        for row in rows:
            formatted_row = "  ".join(str(row[i]).ljust(col_widths[i]) for i in range(len(row)))
            echo_rich_text(formatted_row)


@cli.command(short_help="Start a node process")
@ape_cli_context()
@network_option(default="ethereum:local:node")
@click.option("--block-time", default=None, type=int, help="Block time in seconds")
@click.option("--background", is_flag=True, help="Run in the background")
def run(cli_ctx, provider, block_time, background):
    """
    Start a subprocess node as if running independently
    and stream stdout and stderr.
    """
    from ape.api.providers import SubprocessProvider

    # Ignore extra loggers, such as web3 loggers.
    cli_ctx.logger._extra_loggers = {}
    if not isinstance(provider, SubprocessProvider):
        cli_ctx.abort(
            f"`ape networks run` requires a provider that manages a process, not '{provider.name}'."
        )
    elif provider.is_connected:
        cli_ctx.abort("Process already running.")

    # Set block time if provided
    if block_time is not None:
        provider.provider_settings.update({"block_time": block_time})

    # Start showing process logs.
    original_level = cli_ctx.logger.level
    original_format = cli_ctx.logger.fmt
    cli_ctx.logger.set_level(LogLevel.DEBUG)

    # Change format to exclude log level (since it is always just DEBUG)
    cli_ctx.logger.format(fmt="%(message)s")

    try:
        _run(cli_ctx, provider, background=background)
    finally:
        cli_ctx.logger.set_level(original_level)
        cli_ctx.logger.format(fmt=original_format)


def _run(cli_ctx, provider: "SubprocessProvider", background: bool = False):
    provider.background = background
    provider.connect()

    if process := provider.process:
        if background:
            # End this process, letting the node continue running.
            # This node can be killed later using the `ape networks kill` command.
            return

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


@cli.command(short_help="Stop node processes")
@ape_cli_context()
@click.argument("process_ids", nargs=-1, type=int)
@click.option("--all", "kill_all", is_flag=True, help="Kill all running processes")
@network_option(default=None)
def kill(cli_ctx, process_ids, kill_all):
    """
    Stop node processes
    """
    if kill_all:
        if process_ids:
            raise click.BadOptionUsage("--all", "Cannot use `--all` with PID arguments.")

        process_ids = cli_ctx.network_manager.running_nodes.process_ids

    if not process_ids:
        message = (
            "No running nodes found."
            if not cli_ctx.network_manager.running_nodes
            else "No processes given. Use `--all` to kill all processes."
        )
        echo_rich_text(message)
        return

    elif processes_killed := cli_ctx.network_manager.kill_node_process(*process_ids):
        # Killed 1 or more nodes.
        click.echo("Stopped the following node(s):")
        pids_stopped = set()
        for pid, data in processes_killed.items():
            echo_rich_text(f"\t{repr(data)}")
            pids_stopped.add(pid)

        if rest := [pid for pid in process_ids if pid not in pids_stopped]:
            click.echo(f"The remaining process IDs were no longer valid: {','.join(rest)}.")

    else:
        # Terminated the process outside of Ape.
        click.echo("No running nodes found, but cleaned up cache.")


@cli.command(short_help="Check if a provider is available")
@ape_cli_context()
@network_option()
def ping(cli_ctx, provider):
    if hasattr(provider, "allow_start"):
        # We don't want to allow starting processes; this is used for
        # checking if processes are alive (as well as checking live URIs).
        provider.allow_start = False

    provider.connect()
    status = "AVAILABLE" if provider.is_connected else "UNAVAILABLE"
    click.echo(f"'{provider.network_choice}' connection status: {status}")
