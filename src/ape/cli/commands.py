from typing import Any

import click
from click import Context

from ape import networks


class NetworkBoundCommand(click.Command):
    """A command that uses the network option.
    It will automatically set the network for the duration of the command execution.
    """

    def invoke(self, ctx: Context) -> Any:
        with networks.parse_network_choice(ctx.params["network"]):
            super().invoke(ctx)
