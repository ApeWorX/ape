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
        value = ctx.params["network"]
        with networks.parse_network_choice(value):
            super().invoke(ctx)
