from typing import Iterator, Tuple, Type

from ape.api import QueryAPI

from .pluggy_patch import PluginType, hookspec


class QueryPlugin(PluginType):
    """
    A plugin for querying chains.
    """

    @hookspec
    def query_engines(self) -> Iterator[Tuple[str, Type[QueryAPI]]]:
        """
        A hook that returns an iterator of types of a string query type and a ``QueryAPI`` subclass

        Usage example::

            @plugins.register(plugins.QueryPlugin)
            def query_engines():
                yield postgres, PostgresEngine

        Returns:
            Iterator[tuple[str, Type[:class:`~ape.api.query.QueryAPI`]]]
        """
