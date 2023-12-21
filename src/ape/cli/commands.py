import inspect
import warnings
from typing import Any, List, Optional

import click
from click import Context

from ape import networks
from ape.api import ProviderAPI, ProviderContextManager
from ape.cli.choices import NetworkChoice
from ape.exceptions import NetworkError


def get_param_from_ctx(ctx: Context, param: str) -> Optional[Any]:
    if value := ctx.params.get(param):
        return value

    # If not found, check the parent context.
    elif parent := ctx.parent:
        return get_param_from_ctx(parent, param)

    return None


def parse_network(ctx: Context) -> ProviderContextManager:
    interactive = get_param_from_ctx(ctx, "interactive")

    # Handle if already parsed (as when using network-option)
    if ctx.obj and "provider" in ctx.obj:
        provider = ctx.obj["provider"]
        return provider.network.use_provider(provider, disconnect_on_exit=not interactive)

    provider = get_param_from_ctx(ctx, "network")
    if provider is not None and isinstance(provider, ProviderAPI):
        return provider.network.use_provider(provider, disconnect_on_exit=not interactive)
    elif provider is not None and isinstance(provider, str):
        return networks.parse_network_choice(provider, disconnect_on_exit=not interactive)
    elif provider is None:
        ecosystem = networks.default_ecosystem
        network = ecosystem.default_network
        if provider_name := network.default_provider_name:
            return network.use_provider(provider_name, disconnect_on_exit=not interactive)
        else:
            raise NetworkError(f"Network {network.name} has no providers.")
    else:
        raise TypeError(f"Unknown type for network choice: '{provider}'.")


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
            # Add the option automatically.
            from ape.cli.options import NetworkOption

            option = NetworkOption(base_type=base_type, callback=self._network_callback)
            self.params.append(option)

        return super().parse_args(ctx, args)

    def invoke(self, ctx: Context) -> Any:
        with parse_network(ctx) as provider:
            if self.callback is None:
                return

            # Will be put back with correct value if needed.
            # Else, causes issues.
            ctx.params.pop("network", None)

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
                ctx.params["network"] = provider.network_choice

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
