from typing import Any

import click
from click import Context

from ape import networks


def check_parents_for_interactive(ctx: Context) -> bool:
    interactive: bool = ctx.params.get("interactive", False)
    if interactive:
        return True
    # If not found, check the parent context.
    if interactive is None and ctx.parent:
        return check_parents_for_interactive(ctx.parent)
    return False


class NetworkBoundCommand(click.Command):
    """
    A command that uses the :meth:`~ape.cli.options.network_option`.
    It will automatically set the network for the duration of the command execution.
    """

    def invoke(self, ctx: Context) -> Any:
        value = ctx.params.get("network") or networks.default_ecosystem.name
        interactive = check_parents_for_interactive(ctx)
        with networks.parse_network_choice(value, disconnect_on_exit=not interactive):
            super().invoke(ctx)
