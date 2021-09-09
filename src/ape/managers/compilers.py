from pathlib import Path
from typing import Dict, List, Set

from dataclassy import dataclass

from ape.api.compiler import CompilerAPI
from ape.plugins import PluginManager
from ape.types import ContractType
from ape.utils import cached_property, notify

from ..exceptions import CompilerError
from .config import ConfigManager


@dataclass
class CompilerManager:
    config: ConfigManager
    plugin_manager: PluginManager

    @cached_property
    def registered_compilers(self) -> Dict[str, CompilerAPI]:
        registered_compilers = {}

        for plugin_name, (extensions, compiler_class) in self.plugin_manager.register_compiler:
            # TODO: Add config via ``self.config.get_config(plugin_name)``
            compiler = compiler_class()

            for extension in extensions:

                if extension in registered_compilers:
                    raise CompilerError(f"Compiler for '{extension}' is already registered")

                registered_compilers[extension] = compiler

        return registered_compilers

    def compile(self, contract_filepaths: List[Path]) -> Dict[str, ContractType]:
        extensions = self._get_contract_extensions(contract_filepaths)

        contract_types = {}
        for extension in extensions:
            paths_to_compile = [path for path in contract_filepaths if path.suffix == extension]
            for path in paths_to_compile:
                notify("INFO", f"Compiling '{self._get_contract_path(path)}'")

            for contract_type in self.registered_compilers[extension].compile(paths_to_compile):

                if contract_type.contractName in contract_types:
                    raise CompilerError("ContractType collision across compiler plugins")

                contract_types[contract_type.contractName] = contract_type

        return contract_types

    def _get_contract_extensions(self, contract_filepaths: List[Path]) -> Set[str]:
        extensions = set(path.suffix for path in contract_filepaths)
        unhandled_extensions = extensions - set(self.registered_compilers)
        if len(unhandled_extensions) > 0:
            unhandled_extensions_str = ", ".join(unhandled_extensions)
            raise CompilerError(f"No compiler found for extensions [{unhandled_extensions_str}]")

        return extensions

    def _get_contract_path(self, path: Path):
        try:
            return path.relative_to(self.config.PROJECT_FOLDER)
        except ValueError:
            return path
