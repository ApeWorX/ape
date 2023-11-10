from typing import Any

import click
from click import Context

from ape import networks


class NetworkBoundCommand(click.Command):
    """
    A command that uses the :meth:`~ape.cli.options.network_option`.
    It will automatically set the network for the duration of the command execution.
    """

    def invoke(self, ctx: Context) -> Any:
        value = ctx.params.get("network") or networks.default_ecosystem.name
        interactive = ctx.params.get("interactive")
        # If not found, check the parent context.
        if interactive is None and ctx.parent:
            interactive = ctx.parent.params.get("interactive")
        with networks.parse_network_choice(value, disconnect_on_exit=not interactive):
            super().invoke(ctx)
