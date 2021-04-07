from typing import Type

from ape.api.compiler import CompilerAPI

from .pluggy_patch import hookspec


class CompilerPlugin:
    @hookspec
    def register_compiler(self) -> Type[CompilerAPI]:
        """
        Returns a compiler class that can be used to compile smart contracts.
        """
