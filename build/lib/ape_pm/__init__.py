from ape import plugins

from .compiler import InterfaceCompiler


@plugins.register(plugins.CompilerPlugin)
def register_compiler():
    return (".json",), InterfaceCompiler
