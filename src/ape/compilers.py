from typing import Iterator, List

from ape.plugins.compiler_api import CompilerAPI
from ape import plugins


def load(contract_type: str) -> CompilerAPI:
    if contract_type == "":
        raise ValueError("Cannot use empty string as contract_type!")

    for plugin in plugins.registered_plugins[plugins.CompilerPlugin]:
        compiler = plugin.data
        if compiler.handles(contract_type):
            return compiler()

    raise IndexError(f"No compiler supporting contract type `{contract_type}`.")
