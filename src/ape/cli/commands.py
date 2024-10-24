import inspect
from importlib import import_module
from typing import TYPE_CHECKING, Any, Optional

import click
from click import Context

from ape.cli.choices import _NONE_NETWORK, NetworkChoice
from ape.exceptions import NetworkError
from ape.utils.basemodel import ManagerAccessMixin as access

if TYPE_CHECKING:
    from ape.api.networks import ProviderContextManager
    from ape.api.providers import ProviderAPI


def get_param_from_ctx(ctx: Context, param: str) -> Optional[Any]:
    if value := ctx.params.get(param):
        return value

    # If not found, check the parent context.
    elif parent := ctx.parent:
        return get_param_from_ctx(parent, param)

    return None


def parse_network(ctx: Context) -> Optional["ProviderContextManager"]:
    interactive = get_param_from_ctx(ctx, "interactive")

    # Handle if already parsed (as when using network-option)
    if ctx.obj and "provider" in ctx.obj:
        provider = ctx.obj["provider"]
        return provider.network.use_provider(provider, disconnect_on_exit=not interactive)

    provider = get_param_from_ctx(ctx, "network")
    provider_module = import_module("ape.api.providers")
    if provider is not None and isinstance(provider, provider_module.ProviderAPI):
        return provider.network.use_provider(provider, disconnect_on_exit=not interactive)

    elif provider not in (None, _NONE_NETWORK) and isinstance(provider, str):
        # Is using a choice-str network param value instead of the network object instances.
        return access.network_manager.parse_network_choice(
            provider, disconnect_on_exit=not interactive
        )

    elif provider is None:
        ecosystem = access.network_manager.default_ecosystem
        network = ecosystem.default_network
        if provider_name := network.default_provider_name:
            return network.use_provider(provider_name, disconnect_on_exit=not interactive)
        else:
            raise NetworkError(f"Network {network.name} has no providers.")
    elif provider == _NONE_NETWORK:
        # Was told to skip connection.
        return None
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

    def parse_args(self, ctx: Context, args: list[str]) -> list[str]:
        arguments = args  # Renamed for better pdb support.
        provider_module = import_module("ape.api.providers")
        base_type = provider_module.ProviderAPI if self._use_cls_types else str
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

        return super().parse_args(ctx, arguments)

    def invoke(self, ctx: Context) -> Any:
        if self.callback is None:
            return

        elif network_ctx := parse_network(ctx):
            with network_ctx as provider:
                return self._invoke(ctx, provider=provider)
        else:
            return self._invoke(ctx)

    def _invoke(self, ctx: Context, provider: Optional["ProviderAPI"] = None):
        # Will be put back with correct value if needed.
        # Else, causes issues.
        ctx.params.pop("network", None)

        valid_fields = ("ecosystem", "network", "provider")
        requested_fields = (
            []
            if self.callback is None
            else [x for x in inspect.signature(self.callback).parameters if x in valid_fields]
        )
        if self._use_cls_types and requested_fields:
            options = (
                {}
                if provider is None
                else {
                    "ecosystem": provider.network.ecosystem,
                    "network": provider.network,
                    "provider": provider,
                }
            )
            for name in requested_fields:
                if (
                    name not in ctx.params
                    or ctx.params[name] is None
                    or isinstance(ctx.params[name], str)
                ):
                    ctx.params[name] = options.get(name)

        elif not self._use_cls_types and provider is not None:
            # Keep choice-str instead of parsing to objects.
            ctx.params["network"] = provider.network_choice

        return ctx.invoke(self.callback or (lambda: None), **ctx.params)
