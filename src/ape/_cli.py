import difflib
import re
import sys
import warnings
from collections.abc import Iterable
from gettext import gettext
from importlib import import_module
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Optional

import click
import rich
import yaml
from click import Context

from ape.cli.options import ape_cli_context
from ape.exceptions import Abort, ApeException, ConfigError, handle_ape_exception
from ape.logging import logger
from ape.utils.basemodel import ManagerAccessMixin as access

_DIFFLIB_CUT_OFF = 0.6


def display_config(ctx, param, value):
    # NOTE: This is necessary not to interrupt how version or help is intercepted
    if not value or ctx.resilient_parsing:
        return

    click.echo("# Current configuration")

    # NOTE: Using json-mode as yaml.dump requires JSON-like structure.
    model = access.local_project.config.model_dump(mode="json")

    click.echo(yaml.dump(model))
    ctx.exit()  # NOTE: Must exit to bypass running ApeCLI


def _validate_config():
    project = access.local_project
    try:
        _ = project.config
    except ConfigError as err:
        rich.print(err)
        # Exit now to avoid weird problems.
        sys.exit(1)


class ApeCLI(click.MultiCommand):
    _commands: Optional[dict] = None
    _CLI_GROUP_NAME = "ape_cli_subcommands"

    def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
        # Validate the config before any argument parsing,
        # as arguments may utilize config.
        if "--help" not in args and args != []:
            # perf: don't bother w/ config if only doing --help.
            _validate_config()

        return super().parse_args(ctx, args)

    def format_commands(self, ctx, formatter) -> None:
        commands = []
        for subcommand in self.list_commands(ctx):
            cmd = self.get_command(ctx, subcommand)
            if cmd is None or cmd.hidden:
                continue

            commands.append((subcommand, cmd))

        if not commands:
            return None

        limit = formatter.width - 6 - max(len(cmd[0]) for cmd in commands)

        # Split the commands into 3 sections.
        sections: dict[str, list[tuple[str, str]]] = {
            "Core": [],
            "Plugin": [],
            "3rd-Party Plugin": [],
        }
        plugin_utils = import_module("ape.plugins._utils")
        metadata_cls = plugin_utils.PluginMetadataList
        plugin_manager = access.plugin_manager
        pl_metadata = metadata_cls.load(plugin_manager, include_available=False)
        for cli_name, cmd in commands:
            help = cmd.get_short_help_str(limit)
            plugin = pl_metadata.get_plugin(cli_name, check_available=False)
            if plugin is None:
                continue

            if plugin.in_core:
                sections["Core"].append((cli_name, help))
            elif plugin.is_installed and not plugin.is_third_party:
                sections["Plugin"].append((cli_name, help))
            else:
                sections["3rd-Party Plugin"].append((cli_name, help))

        for title, rows in sections.items():
            if not rows:
                continue

            with formatter.section(gettext(f"{title} Commands")):
                formatter.write_dl(rows)

    def invoke(self, ctx) -> Any:
        try:
            return super().invoke(ctx)
        except click.UsageError as err:
            self._suggest_cmd(err)
        except ApeException as err:
            path = ctx.obj.local_project.path

            # NOTE: isinstance check for type-checkers.
            if isinstance(path, Path) and handle_ape_exception(err, (path,)):
                # All exc details already outputted.
                sys.exit(1)
            else:
                raise Abort.from_ape_exception(err) from err

    @staticmethod
    def _suggest_cmd(usage_error):
        if usage_error.message is None:
            raise usage_error

        elif not (match := re.match("No such command '(.*)'.", usage_error.message)):
            raise usage_error

        groups = match.groups()
        if len(groups) < 1:
            raise usage_error

        bad_arg = groups[0]
        suggested_commands = difflib.get_close_matches(
            bad_arg, list(usage_error.ctx.command.commands.keys()), cutoff=_DIFFLIB_CUT_OFF
        )
        if suggested_commands:
            if bad_arg not in suggested_commands:
                usage_error.message = (
                    f"No such command '{bad_arg}'. Did you mean {' or '.join(suggested_commands)}?"
                )

        raise usage_error

    @property
    def commands(self) -> dict:
        if self._commands:
            return self._commands

        _entry_points = entry_points()
        eps: Iterable
        if select_fn := getattr(_entry_points, "select", None):
            # NOTE: Using getattr because mypy.
            eps = select_fn(group=self._CLI_GROUP_NAME)
        else:
            # Python 3.9. Can remove once we drop support.
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                eps = _entry_points.get(self._CLI_GROUP_NAME, [])  # type: ignore

        commands = {cmd.name.replace("_", "-").replace("ape-", ""): cmd.load for cmd in eps}
        self._commands = {k: commands[k] for k in sorted(commands)}
        return self._commands

    def list_commands(self, ctx) -> list[str]:
        return [k for k in self.commands]

    def get_command(self, ctx, name) -> Optional[click.Command]:
        try:
            return self.commands[name]()
        except Exception as err:
            logger.warn_from_exception(err, f"Unable to load CLI endpoint for plugin 'ape_{name}'")

        # NOTE: don't return anything so Click displays proper error
        return None


@click.command(cls=ApeCLI, context_settings=dict(help_option_names=["-h", "--help"]))
@ape_cli_context()
@click.version_option(message="%(version)s", package_name="eth-ape")
@click.option(
    "--config",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=display_config,
    help="Show configuration options (using `ape-config.yaml`)",
)
def cli(context):
    _ = context
