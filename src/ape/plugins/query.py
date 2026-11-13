from collections.abc import Iterator
from typing import TYPE_CHECKING

from .pluggy_patch import PluginType, hookspec

if TYPE_CHECKING:
    from ape.api.query import QueryEngineAPI


class QueryPlugin(PluginType):
    """
    A plugin for querying chains.
    """

    @hookspec
    def query_engines(self) -> Iterator[type["QueryEngineAPI"]]:  # type: ignore[empty-body]
        """
        A hook that returns an iterator of types of ``QueryEngineAPI`` subclasses

        Usage example::

            @plugins.register(plugins.QueryPlugin)
            def query_engines():
                yield PostgresEngine

        Returns:
            Iterator[type[:class:`~ape.api.query.QueryEngineAPI`]]
        """
