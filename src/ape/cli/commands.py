import inspect
import warnings
from typing import Any, List

import click
from click import Context

from ape import networks
from ape.api import ProviderAPI
from ape.exceptions import NetworkError


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

    def __init__(self, *args, **kwargs):
        self._use_cls_types = kwargs.pop("use_cls_types", True)
        super().__init__(*args, **kwargs)

    def parse_args(self, ctx: Context, args: List[str]) -> List[str]:
        if not any(
            isinstance(param, click.core.Option) and param.name == "network"
            for param in self.params
        ):
            from ape.cli.options import NetworkOption

            base_type = ProviderAPI if self._use_cls_types else str
            option = NetworkOption(base_type=base_type)
            self.params.append(option)

        return super().parse_args(ctx, args)

    def invoke(self, ctx: Context) -> Any:
        interactive = check_parents_for_interactive(ctx)
        param = ctx.params.get("network")
        if param is not None and isinstance(param, ProviderAPI):
            provider = param
            network_context = provider.network.use_provider(
                provider, disconnect_on_exit=not interactive
            )
        elif param is not None and isinstance(param, str):
            network_context = networks.parse_network_choice(param)
        elif param is None:
            ecosystem = networks.default_ecosystem
            network = ecosystem.default_network
            if provider_name := network.default_provider_name:
                network_context = network.use_provider(provider_name)
            else:
                raise NetworkError(f"Network {network.name} has no providers.")
        else:
            raise TypeError(f"Unknown type for network choice: '{param}'.")

        with network_context:
            if self.callback is not None:
                signature = inspect.signature(self.callback)
                callback_args = [x.name for x in signature.parameters.values()]

                opt_name = "network"
                param = ctx.params.pop(opt_name, None)
                if param is None:
                    ecosystem = networks.default_ecosystem
                    network = ecosystem.default_network
                    # Use default
                    if default_provider := network.default_provider:
                        provider = default_provider
                    else:
                        # Unlikely to get here.
                        raise ValueError(
                            f"Missing default provider for network '{network.choice}'. "
                            f"Using 'ethereum:local:test'."
                        )

                elif isinstance(param, ProviderAPI):
                    provider = param

                elif isinstance(param, str):
                    # Is a choice str
                    provider = networks.parse_network_choice(param)._provider
                else:
                    raise TypeError(f"Can't handle type of parameter '{param}'.")

                if self._use_cls_types:
                    if "ecosystem" in callback_args:
                        ctx.params["ecosystem"] = provider.network.ecosystem
                    if "network" in callback_args:
                        ctx.params["network"] = provider.network
                    if "provider" in callback_args:
                        ctx.params["provider"] = provider

                    # If none of the above, the user doesn't use any network value.

                else:
                    # Legacy behavior, but may have a purpose.
                    ctx.params[opt_name] = provider.network_choice

                return ctx.invoke(self.callback, **ctx.params)


# TODO: 0.8 delete
class NetworkBoundCommand(ConnectedProviderCommand):
    def __init__(self, *args, **kwargs):
        warnings.warn(
            "'NetworkBoundCommand' is deprecated. Use 'ConnectedProviderCommand'.",
            DeprecationWarning,
        )

        # Disable the advanced network class types so it behaves legacy.
        kwargs["use_cls_types"] = False

        super().__init__(*args, **kwargs)
