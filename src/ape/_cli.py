import difflib
import re
import traceback
from typing import Any, Dict

import click
import yaml

from ape.cli import Abort, ape_cli_context
from ape.exceptions import ApeException
from ape.logging import LogLevel, logger
from ape.plugins import clean_plugin_name

try:
    from importlib import metadata  # type: ignore
except ImportError:
    import importlib_metadata as metadata  # type: ignore

_DIFFLIB_CUT_OFF = 0.6


def display_config(ctx, param, value):
    # NOTE: This is necessary not to interrupt how version or help is intercepted
    if not value or ctx.resilient_parsing:
        return

    from ape import project

    click.echo("# Current configuration")
    click.echo(yaml.dump(project.config_manager.dict()))

    ctx.exit()  # NOTE: Must exit to bypass running ApeCLI


class ApeCLI(click.MultiCommand):
    _commands = None

    def invoke(self, ctx) -> Any:
        try:
            return super().invoke(ctx)
        except click.UsageError as err:
            self._suggest_cmd(err)
        except ApeException as err:
            if logger.level == LogLevel.DEBUG.value:
                tb = traceback.format_exc()
                err_message = tb or str(err)
            else:
                err_message = str(err)

            raise Abort(f"({type(err).__name__}) {err_message}") from err

    @staticmethod
    def _suggest_cmd(usage_error):
        if usage_error.message is None:
            raise usage_error

        match = re.match("No such command '(.*)'.", usage_error.message)
        if not match:
            raise usage_error

        bad_arg = match.groups()[0]
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
    def commands(self) -> Dict:
        group_name = "ape_cli_subcommands"
        if not self._commands:
            try:
                entry_points = metadata.entry_points(group=group_name)  # type: ignore
            except TypeError:
                entry_points = metadata.entry_points()
                entry_points = (
                    entry_points[group_name] if group_name in entry_points else []  # type: ignore
                )

            if not entry_points:
                raise Abort("Missing registered cli subcommands")

            self._commands = {
                clean_plugin_name(entry_point.name): entry_point.load  # type: ignore
                for entry_point in entry_points
            }

        return self._commands

    def list_commands(self, ctx):
        return list(sorted(self.commands))

    def get_command(self, ctx, name):
        if name in self.commands:
            try:
                return self.commands[name]()
            except Exception as err:
                logger.warn_from_exception(
                    err, f"Unable to load CLI endpoint for plugin 'ape_{name}'"
                )

        # NOTE: don't return anything so Click displays proper error


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
