from typing import Any, Dict

import click
import yaml

from ape.exceptions import ApeException
from ape.plugins import clean_plugin_name
from ape.utils import Abort, notify

try:
    from importlib import metadata  # type: ignore
except ImportError:
    import importlib_metadata as metadata  # type: ignore


def display_config(ctx, param, value):
    # NOTE: This is necessary not to interrupt how version or help is intercepted
    if not value or ctx.resilient_parsing:
        return

    from ape import project

    click.echo("# Current configuration")
    click.echo(yaml.dump(project.config.serialize()))

    ctx.exit()  # NOTE: Must exit to bypass running ApeCLI


class ApeCLI(click.MultiCommand):
    _commands = None

    def invoke(self, ctx: click.Context) -> Any:
        try:
            return super().invoke(ctx)
        except ApeException as err:
            raise Abort(str(err)) from err

    @property
    def commands(self) -> Dict:
        if not self._commands:
            entry_points = metadata.entry_points()

            if "ape_cli_subcommands" not in entry_points:
                raise Abort("Missing registered cli subcommands")

            self._commands = {
                clean_plugin_name(entry_point.name): entry_point.load
                for entry_point in entry_points["ape_cli_subcommands"]
            }

        return self._commands

    def list_commands(self, ctx):
        return list(sorted(self.commands))

    def get_command(self, ctx, name):
        if name in self.commands:
            try:
                return self.commands[name]()
            except Exception as err:
                notify(
                    "WARNING",
                    f"Unable to load CLI endpoint for plugin 'ape_{name}'.\n\t{err}",
                )

        # NOTE: don't return anything so Click displays proper error


@click.command(cls=ApeCLI, context_settings=dict(help_option_names=["-h", "--help"]))
@click.version_option(message="%(version)s", package_name="eth-ape")
@click.option(
    "--config",
    is_flag=True,
    is_eager=True,
    expose_value=False,
    callback=display_config,
    help="Show configuration options (using `ape-config.yaml`)",
)
def cli():
    pass
