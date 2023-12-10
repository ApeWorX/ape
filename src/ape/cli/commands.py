import inspect
from typing import Any, List

import click
from click import Context

from ape import networks
from ape.api import ProviderAPI


def check_parents_for_interactive(ctx: Context) -> bool:
    interactive: bool = ctx.params.get("interactive", False)
    if interactive:
        return True

    # If not found, check the parent context.
    if interactive is None and ctx.parent:
        return check_parents_for_interactive(ctx.parent)

    return False


class ConnectedProviderCommand(click.Command):
    """
    A command that uses the :meth:`~ape.cli.options.network_option`.
    It will automatically set the network for the duration of the command execution.
    """

    def parse_args(self, ctx: Context, args: List[str]) -> List[str]:
        if not any(
            isinstance(param, click.core.Option) and param.name == "network"
            for param in self.params
        ):
            from ape.cli.options import NetworkOption

            option = NetworkOption()
            self.params.append(option)

        return super().parse_args(ctx, args)

    def invoke(self, ctx: Context) -> Any:
        default = networks.default_ecosystem.default_network.default_provider
        param = ctx.params.get("network")
        provider: ProviderAPI = param or default  # type: ignore
        interactive = check_parents_for_interactive(ctx)
        with provider.network.use_provider(provider.name, disconnect_on_exit=not interactive):
            if self.callback is not None:
                signature = inspect.signature(self.callback)
                callback_args = [x.name for x in signature.parameters.values()]

                opt_name = "network"
                provider = ctx.params.pop(opt_name)

                if "ecosystem" in callback_args:
                    ctx.params["ecosystem"] = provider.network.ecosystem
                if "network" in callback_args:
                    ctx.params["network"] = provider.network
                if "provider" in callback_args:
                    ctx.params["provider"] = provider

                # If none of he above, the user doesn't use any network value.

                return ctx.invoke(self.callback, **ctx.params)
