from ape import plugins

from .compiler import InterfaceCompiler, InterfaceCompilerConfig


@plugins.register(plugins.Config)
def config_class():
    return InterfaceCompilerConfig


@plugins.register(plugins.CompilerPlugin)
def register_compiler():
    return (".json",), InterfaceCompiler
