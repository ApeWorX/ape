from typing import TYPE_CHECKING, Iterator, Type

from .pluggy_patch import PluginType, hookspec

if TYPE_CHECKING:
    from ape.api import QueryAPI


class QueryPlugin(PluginType):
    """
    A plugin for querying chains.
    """

    @hookspec
    def query_engines(self) -> Iterator[Type["QueryAPI"]]:
        """
        A hook that returns an iterator of types of a ``QueryAPI`` subclasses

        Usage example::

            @plugins.register(plugins.QueryPlugin)
            def query_engines():
                yield PostgresEngine

        Returns:
            Iterator[Type[:class:`~ape.api.query.QueryAPI`]]
        """
