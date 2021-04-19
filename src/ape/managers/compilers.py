from pathlib import Path
from typing import Dict

from dataclassy import dataclass

from ape.api.compiler import CompilerAPI
from ape.plugins import PluginManager
from ape.types import ContractType
from ape.utils import cached_property, notify

from .config import ConfigManager


@dataclass
class CompilerManager:
    config: ConfigManager
    plugin_manager: PluginManager

    @cached_property
    def registered_compilers(self) -> Dict[str, CompilerAPI]:
        registered_compilers = {}

        for plugin_name, (extensions, compiler_class) in self.plugin_manager.register_compiler:
            # TODO: Add config via `self.config.get_config(plugin_name)`
            compiler = compiler_class()

            for extension in extensions:

                if extension in registered_compilers:
                    raise  # Extension already registered!

                registered_compilers[extension] = compiler

        return registered_compilers

    def compile(self, contract_filepath: Path) -> ContractType:
        extension = contract_filepath.suffix

        if extension in self.registered_compilers:
            notify("INFO", f"Compiling '{contract_filepath.relative_to(Path.cwd())}'")
            return self.registered_compilers[extension].compile(contract_filepath)

        else:
            raise  # No compiler found for extension
