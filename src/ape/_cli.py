import difflib
import re
import sys
from collections.abc import Iterable
from functools import cached_property
from gettext import gettext
from importlib.metadata import entry_points
from pathlib import Path
from typing import Any, Optional
from warnings import catch_warnings, simplefilter

import click
import yaml

from ape.cli.options import ape_cli_context
from ape.exceptions import Abort, ApeException, handle_ape_exception
from ape.logging import logger

_DIFFLIB_CUT_OFF = 0.6


def display_config(ctx, param, value):
    # NOTE: This is necessary not to interrupt how version or help is intercepted
    if not value or ctx.resilient_parsing:
        return

    from ape.utils.basemodel import ManagerAccessMixin as access

    click.echo("# Current configuration")

    # NOTE: Using json-mode as yaml.dump requires JSON-like structure.
    model = access.local_project.config.model_dump(mode="json")

    click.echo(yaml.dump(model))
    ctx.exit()  # NOTE: Must exit to bypass running ApeCLI


class ApeCLI(click.MultiCommand):
    _CLI_GROUP_NAME = "ape_cli_subcommands"

    def format_commands(self, ctx, formatter) -> None:
        from ape.plugins._utils import PluginMetadataList

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
        pl_metadata = PluginMetadataList.from_package_names(f"ape_{c[0]}" for c in commands)
        for cli_name, cmd in commands:
            help = cmd.get_short_help_str(limit)
            plugin = pl_metadata.get_plugin(cli_name, check_available=False)
            if plugin is None:
                continue

            if plugin.in_core:
                sections["Core"].append((cli_name, help))
            elif plugin.check_trusted(use_web=False):
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

    @cached_property
    def commands(self) -> dict:
        _entry_points = entry_points()
        eps: Iterable

        try:
            eps = _entry_points.select(group=self._CLI_GROUP_NAME)
        except AttributeError:
            # Fallback for Python 3.9
            with catch_warnings():
                simplefilter("ignore")
                eps = _entry_points.get(self._CLI_GROUP_NAME, [])  # type: ignore

        commands = {cmd.name.replace("_", "-").replace("ape-", ""): cmd.load for cmd in eps}
        return dict(sorted(commands.items()))

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
