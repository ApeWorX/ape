from ape import plugins

from .compiler import PackageCompiler


@plugins.register(plugins.CompilerPlugin)
def register_compiler():
    return (".json",), PackageCompiler
