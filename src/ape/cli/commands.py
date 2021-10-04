from typing import Any

import click
from click import Context

from ape import networks
from ape.cli.options import network_option


def network_bound_command(*args, **kwargs):
    """
    A command that automatically has the `network_option` and
    executes the command method entirely in the context of the
    given network.
    """

    def decorator(f):
        f = click.command(cls=NetworkBoundCommand, *args, **kwargs)(f)
        f = network_option(f)
        return f

    return decorator


class NetworkBoundCommand(click.Command):
    """A command that uses the network option.
    It will automatically set the network for the duration of the command execution.
    """

    def invoke(self, ctx: Context) -> Any:
        with networks.parse_network_choice(ctx.params["network"]):
            super().invoke(ctx)
