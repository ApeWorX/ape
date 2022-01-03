from pathlib import Path
from typing import Dict, List, Set

from dataclassy import dataclass

from ape.api import CompilerAPI
from ape.exceptions import CompilerError
from ape.logging import logger
from ape.plugins import PluginManager
from ape.types import ContractType
from ape.utils import cached_property

from .config import ConfigManager


@dataclass
class CompilerManager:
    """
    The singleton that manages :class:`~ape.api.compiler.CompilerAPI` instances.
    Each compiler plugin typically contains a single :class:`~ape.api.compiler.CompilerAPI`.

    **NOTE**: Typically, users compile their projects using the CLI via ``ape compile``,
    which uses the :class:`~ape.api.compiler.CompilerAPI` under-the-hood.

    Usage example::

        from ape import compilers  # "compilers" is the CompilerManager singleton
    """

    config: ConfigManager
    plugin_manager: PluginManager

    def __repr__(self):
        return f"<CompilerManager len(registered_compilers)={len(self.registered_compilers)}>"

    @cached_property
    def registered_compilers(self) -> Dict[str, CompilerAPI]:
        """
        Each compile-able file extension mapped to its respective
        :class:`~ape.api.compiler.CompilerAPI` instance.

        Returns:
            Dict[str, :class:`~ape.api.compiler.CompilerAPI`]: The mapping of file-extensions
            to compiler API classes.
        """

        registered_compilers = {}

        for plugin_name, (extensions, compiler_class) in self.plugin_manager.register_compiler:
            config = self.config.get_config(plugin_name)
            compiler = compiler_class(config=config)

            for extension in extensions:
                if extension not in registered_compilers:
                    registered_compilers[extension] = compiler

        return registered_compilers

    def compile(self, contract_filepaths: List[Path]) -> Dict[str, ContractType]:
        """
        Invoke :meth:`ape.ape.compiler.CompilerAPI.compile` for each of the given files.
        For example, use the `ape-solidity plugin <https://github.com/ApeWorX/ape-solidity>`__
        to compile ``'.sol'`` files.

        Raises:
            :class:`~ape.exceptions.CompilerError`: When there is no compiler found for the given
              extension as well as when there is a contract-type collision across compilers.

        Args:
            contract_filepaths (List[pathlib.Path]): The list of files to compile,
              as ``pathlib.Path`` objects.

        Returns:
            Dict[str, :class:`~ape.types.contract.ContractType`]: A mapping of
            contract names to their type.
        """

        extensions = self._get_contract_extensions(contract_filepaths)

        contract_types = {}
        for extension in extensions:
            paths_to_compile = [path for path in contract_filepaths if path.suffix == extension]
            for path in paths_to_compile:
                logger.info(f"Compiling '{self._get_contract_path(path)}'.")

            for contract_type in self.registered_compilers[extension].compile(paths_to_compile):

                if contract_type.contractName in contract_types:
                    raise CompilerError("ContractType collision across compiler plugins.")

                contract_types[contract_type.contractName] = contract_type

        return contract_types

    def _get_contract_extensions(self, contract_filepaths: List[Path]) -> Set[str]:
        extensions = set(path.suffix for path in contract_filepaths)
        unhandled_extensions = extensions - set(self.registered_compilers)
        if len(unhandled_extensions) > 0:
            unhandled_extensions_str = ", ".join(unhandled_extensions)
            raise CompilerError(f"No compiler found for extensions [{unhandled_extensions_str}].")

        return extensions

    def _get_contract_path(self, path: Path):
        try:
            return path.relative_to(self.config.PROJECT_FOLDER)
        except ValueError:
            return path
