from typing import Any, Callable, TypeVar, cast

import pluggy  # type: ignore

F = TypeVar("F", bound=Callable[..., Any])
hookimpl = cast(Callable[[F], F], pluggy.HookimplMarker("ape"))
hookspec = pluggy.HookspecMarker("ape")

plugin_manager = pluggy.PluginManager("ape")


class PluginType:
    pass
