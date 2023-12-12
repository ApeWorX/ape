import inspect
import warnings
from typing import Any, List

import click
from click import Context

from ape import networks
from ape.api import ProviderAPI
from ape.cli.choices import NetworkChoice
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
        self._network_callback = kwargs.pop("network_callback", None)
        super().__init__(*args, **kwargs)

    def parse_args(self, ctx: Context, args: List[str]) -> List[str]:
        base_type = ProviderAPI if self._use_cls_types else str
        if existing_option := next(
            iter(
                x
                for x in self.params
                if isinstance(x, click.core.Option)
                and x.name == "network"
                and isinstance(x.type, NetworkChoice)
            ),
            None,
        ):
            # Checking instance above, not sure why mypy still mad.
            existing_option.type.base_type = base_type  # type: ignore

        else:
            # Add the option autmatically.
            from ape.cli.options import NetworkOption

            option = NetworkOption(base_type=base_type, callback=self._network_callback)
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

                valid_fields = ("ecosystem", "network", "provider")
                requested_fields = [
                    x for x in inspect.signature(self.callback).parameters if x in valid_fields
                ]
                if self._use_cls_types and requested_fields:
                    options = {
                        "ecosystem": provider.network.ecosystem,
                        "network": provider.network,
                        "provider": provider,
                    }
                    for name in requested_fields:
                        if (
                            name not in ctx.params
                            or ctx.params[name] is None
                            or isinstance(ctx.params[name], str)
                        ):
                            ctx.params[name] = options[name]

                elif not self._use_cls_types:
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
