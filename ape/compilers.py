from typing import Iterator, List

from ape.plugins.compiler_api import CompilerAPI
from ape import plugins


def load(extension: str) -> CompilerAPI:
    if extension == "":
        raise ValueError("Cannot use empty string as extension!")

    for plugin in plugins.registered_plugins[plugins.CompilerPlugin]:
        compiler = plugin.data
        if compiler.extension() == extension:
            return compiler()

    raise IndexError(f"No compiler supporting extension `{extension}`.")
