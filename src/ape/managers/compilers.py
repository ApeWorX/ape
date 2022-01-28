from pathlib import Path
from typing import ClassVar, Dict, List, Set

from ethpm_types import ContractType

from ape.api import CompilerAPI
from ape.exceptions import CompilerError
from ape.logging import logger
from ape.plugins import PluginManager
from ape.utils import injected_before_use

from .config import ConfigManager


def _get_contract_path(path: Path, base_path: Path):
    try:
        return path.relative_to(base_path)
    except ValueError:
        return path


class CompilerManager:
    """
    The singleton that manages :class:`~ape.api.compiler.CompilerAPI` instances.
    Each compiler plugin typically contains a single :class:`~ape.api.compiler.CompilerAPI`.

    **NOTE**: Typically, users compile their projects using the CLI via ``ape compile``,
    which uses the :class:`~ape.api.compiler.CompilerAPI` under-the-hood.

    Usage example::

        from ape import compilers  # "compilers" is the CompilerManager singleton
    """

    config: ClassVar[ConfigManager] = injected_before_use()  # type: ignore
    plugin_manager: ClassVar[PluginManager] = injected_before_use()  # type: ignore
    _registered_compilers_cache: Dict[Path, Dict[str, CompilerAPI]] = {}

    def __repr__(self):
        num_compilers = len(self.registered_compilers)
        return f"<{self.__class__.__name__} len(registered_compilers)={num_compilers}>"

    @property
    def registered_compilers(self) -> Dict[str, CompilerAPI]:
        """
        Each compile-able file extension mapped to its respective
        :class:`~ape.api.compiler.CompilerAPI` instance.

        Returns:
            Dict[str, :class:`~ape.api.compiler.CompilerAPI`]: The mapping of file-extensions
            to compiler API classes.
        """

        cache_key = self.config.PROJECT_FOLDER
        if cache_key in self._registered_compilers_cache:
            return self._registered_compilers_cache[cache_key]

        registered_compilers = {}

        for plugin_name, (extensions, compiler_class) in self.plugin_manager.register_compiler:
            config = self.config.get_config(plugin_name)
            compiler = compiler_class(config=config)

            for extension in extensions:
                if extension not in registered_compilers:
                    registered_compilers[extension] = compiler

        self._registered_compilers_cache[cache_key] = registered_compilers
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
            Dict[str, ``ContractType``]: A mapping of contract names to their type.
        """

        extensions = self._get_contract_extensions(contract_filepaths)
        contract_types_dict = {}
        for extension in extensions:
            paths_to_compile = [path for path in contract_filepaths if path.suffix == extension]

            for path in paths_to_compile:
                contract_path = _get_contract_path(path, self.config.contracts_folder)
                logger.info(f"Compiling '{contract_path}'.")

            compiled_contracts = self.registered_compilers[extension].compile(
                paths_to_compile, base_path=self.config.contracts_folder
            )
            for contract_type in compiled_contracts:

                if contract_type.name in contract_types_dict:
                    raise CompilerError("ContractType collision across compiler plugins.")

                contract_types_dict[contract_type.name] = contract_type

        return contract_types_dict  # type: ignore

    def _get_contract_extensions(self, contract_filepaths: List[Path]) -> Set[str]:
        extensions = set(path.suffix for path in contract_filepaths)
        unhandled_extensions = extensions - set(self.registered_compilers)
        if len(unhandled_extensions) > 0:
            unhandled_extensions_str = ", ".join(unhandled_extensions)
            raise CompilerError(f"No compiler found for extensions [{unhandled_extensions_str}].")

        return extensions
