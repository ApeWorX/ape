from ape.api.compiler import CompilerAPI

from .pluggy_patch import PluginType, hookspec


class CompilerPlugin(PluginType):
    """
    A plugin that implements the :class:`ape.api.CompilerAPI`, such
    as the `ape-solidity plugin <https://github.com/ApeWorX/ape-solidity>`__
    or the `ape-vyper plugin <https://github.com/ApeWorX/ape-vyper>`__.
    """

    @hookspec
    def register_compiler(self) -> tuple[tuple[str], type[CompilerAPI]]:  # type: ignore[empty-body]
        """
        A hook for returning the set of file extensions the plugin handles
        and the compiler class that can be used to compile them.

        Usage example::

            @plugins.register(plugins.CompilerPlugin)
            def register_compiler():
                return (".json",), InterfaceCompiler

        Returns:
            tuple[tuple[str], type[:class:`~ape.api.CompilerAPI`]]
        """
