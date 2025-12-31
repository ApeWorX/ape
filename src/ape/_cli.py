import difflib
import re
import sys
from functools import cached_property
from gettext import gettext
from pathlib import Path
from typing import TYPE_CHECKING, Any

import click
import yaml

from ape.cli.options import ape_cli_context
from ape.exceptions import Abort, ApeAttributeError, ApeException, handle_ape_exception
from ape.logging import logger

if TYPE_CHECKING:
    from importlib.metadata import EntryPoint

_DIFFLIB_CUT_OFF = 0.6


def display_config(ctx, param, value):
    # NOTE: This is necessary not to interrupt how version or help is intercepted
    if not value or ctx.resilient_parsing:
        return

    from ape.utils.basemodel import ManagerAccessMixin as access

    click.echo("# Current configuration")

    # NOTE: Using json-mode as yaml.safe_dump requires JSON-like structure.
    model = access.local_project.config.model_dump(mode="json")

    click.echo(yaml.safe_dump(model))
    ctx.exit()  # NOTE: Must exit to bypass running ApeCLI


class ApeCLI(click.MultiCommand):
    _CLI_GROUP_NAME = "ape_cli_subcommands"

    def format_commands(self, ctx, formatter) -> None:
        # Split the commands into 2 sections.
        sections: dict[str, list[tuple[str, click.Command | click.Group]]] = {
            "Core": [],
            "Plugin": [],
        }
        max_cmd_name_len = 0
        for name, ep in self.cli_entrypoints.items():
            sections["Core" if ep.dist and ep.dist.name == "eth-ape" else "Plugin"].append(
                (name, ep.load())
            )
            max_cmd_name_len = max(max_cmd_name_len, len(name))

        limit = formatter.width - 6 - max_cmd_name_len
        for section_name, commands in sections.items():
            deflist = []
            for name, cmd in sorted(commands, key=lambda t: t[0]):
                if cmd is None or cmd.hidden:
                    continue

                deflist.append((name, cmd.get_short_help_str(limit)))

            if not deflist:
                # NOTE: Avoid issue with empty sections (now Plugins installed)
                continue

            with formatter.section(gettext(f"{section_name} Commands")):
                formatter.write_dl(deflist)

    def invoke(self, ctx) -> Any:
        try:
            return super().invoke(ctx)

        except click.UsageError as err:
            self._suggest_cmd(ctx, err)

        except ApeException as err:
            path = ctx.obj.local_project.path

            # Extract more interesting ApeException.
            err_to_show = err
            while isinstance(err_to_show, ApeException):
                if (
                    not isinstance(err_to_show, ApeAttributeError)
                    or err_to_show.base_err is None
                    or not isinstance(err_to_show.base_err, ApeException)
                ):
                    break

                err_to_show = err_to_show.base_err

            # NOTE: isinstance check for type-checkers.
            if isinstance(path, Path) and handle_ape_exception(err, (path,)):
                # All exc details already outputted.
                sys.exit(1)
            else:
                raise Abort.from_ape_exception(err) from err

    def _suggest_cmd(self, ctx, usage_error):
        if usage_error.message is None:
            raise usage_error

        elif not (match := re.match("No such command '(.*)'.", usage_error.message)):
            raise usage_error

        groups = match.groups()
        if len(groups) < 1:
            raise usage_error

        bad_arg = groups[0]
        suggested_commands = difflib.get_close_matches(
            bad_arg, self.list_commands(ctx), cutoff=_DIFFLIB_CUT_OFF
        )
        if suggested_commands:
            if bad_arg not in suggested_commands:
                usage_error.message = (
                    f"No such command '{bad_arg}'. Did you mean {' or '.join(suggested_commands)}?"
                )

        raise usage_error

    @cached_property
    def cli_entrypoints(self) -> dict[str, "EntryPoint"]:
        # Lazy load for performance
        from importlib.metadata import entry_points

        return {
            ep.name.replace("_", "-").replace("ape-", ""): ep
            for ep in entry_points().select(group=self._CLI_GROUP_NAME)
        }

    def list_commands(self, ctx) -> list[str]:
        return sorted(self.cli_entrypoints)

    def get_command(self, ctx, name) -> click.Command | None:
        if not (ep := self.cli_entrypoints.get(name)):
            # NOTE: don't return anything so Click displays proper error
            return None

        try:
            return ep.load()
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
