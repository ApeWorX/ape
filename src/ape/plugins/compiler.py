from typing import Tuple, Type

from ape.api.compiler import CompilerAPI

from .pluggy_patch import PluginType, hookspec


class CompilerPlugin(PluginType):
    @hookspec
    def register_compiler(self) -> Tuple[Tuple[str], Type[CompilerAPI]]:
        """
        Returns a set of file extensions the plugin handles,
        and the compiler class that can be used to compile them.
        """
