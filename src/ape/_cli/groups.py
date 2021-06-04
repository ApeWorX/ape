import difflib
import re

import click

_DIFFLIB_CUT_OFF = 0.6


class ApeCLI(click.Group):
    """A `click.Group` subclass that all ape commands are part of."""

    def invoke(self, ctx):
        try:
            return super().invoke(ctx)
        except click.UsageError as err:
            self._suggest_cmd(err)

    @staticmethod
    def _suggest_cmd(usage_err):
        """Handles fuzzy suggestion of commands that are close to the bad command entered.
        Borrowed from code42cli python library.
        """
        if usage_err.message is not None:
            match = re.match("No such command '(.*)'.", usage_err.message)
            if match:
                bad_arg = match.groups()[0]
                available_commands = list(usage_err.ctx.command.commands.keys())
                suggested_commands = difflib.get_close_matches(
                    bad_arg, available_commands, cutoff=_DIFFLIB_CUT_OFF
                )
                if not suggested_commands:
                    raise usage_err
                usage_err.message = "No such command '{}'. Did you mean {}?".format(
                    bad_arg, " or ".join(suggested_commands)
                )
        raise usage_err
