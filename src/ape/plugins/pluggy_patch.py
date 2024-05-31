from collections.abc import Callable
from typing import Any, TypeVar, cast

import pluggy

F = TypeVar("F", bound=Callable[..., Any])
hookimpl = cast(Callable[[F], F], pluggy.HookimplMarker("ape"))
hookspec = pluggy.HookspecMarker("ape")

plugin_manager = pluggy.PluginManager("ape")
"""A manager responsible for registering and accessing plugins (singleton)."""


class PluginType:
    """
    The base plugin class in ape. There are several types of plugins available in ape, such
    as the :class:`~ape.plugins.config.Config` or :class:`~ape.plugins.network.EcosystemPlugin`.
    Each one of them subclass this class. It is used to namespace the plugin hooks for the
    registration process, and to ensure overall conformance to type interfaces as much as possible.
    """
