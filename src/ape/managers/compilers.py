from pathlib import Path
from typing import Dict, List, Set

from ethpm_types import ContractType

from ape.api import CompilerAPI
from ape.exceptions import CompilerError
from ape.logging import logger

from .base import BaseManager


def _get_contract_path(path: Path, base_path: Path):
    if base_path not in path.parents:
        return path

    return path.relative_to(base_path)


class CompilerManager(BaseManager):
    """
    The singleton that manages :class:`~ape.api.compiler.CompilerAPI` instances.
    Each compiler plugin typically contains a single :class:`~ape.api.compiler.CompilerAPI`.

    **NOTE**: Typically, users compile their projects using the CLI via ``ape compile``,
    which uses the :class:`~ape.api.compiler.CompilerAPI` under-the-hood.

    Usage example::

        from ape import compilers  # "compilers" is the CompilerManager singleton
    """

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

        cache_key = self.config_manager.PROJECT_FOLDER
        if cache_key in self._registered_compilers_cache:
            return self._registered_compilers_cache[cache_key]

        registered_compilers = {}

        for plugin_name, (extensions, compiler_class) in self.plugin_manager.register_compiler:

            # TODO: Investigate side effects of loading compiler plugins.
            #       See if this needs to be refactored.
            self.config_manager.get_config(plugin_name=plugin_name)

            compiler = compiler_class()

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

            # Filter out in-source cache files from dependencies.
            paths_to_compile = [
                path
                for path in contract_filepaths
                if path.suffix == extension and ".cache" not in [p.name for p in path.parents]
            ]

            for path in paths_to_compile:
                contract_path = _get_contract_path(path, self.config_manager.contracts_folder)
                logger.info(f"Compiling '{contract_path}'.")

            compiled_contracts = self.registered_compilers[extension].compile(
                paths_to_compile, base_path=self.config_manager.contracts_folder
            )
            for contract_type in compiled_contracts:

                if contract_type.name in contract_types_dict:
                    raise CompilerError("ContractType collision across compiler plugins.")

                contract_types_dict[contract_type.name] = contract_type

        return contract_types_dict  # type: ignore

    def _get_contract_extensions(self, contract_filepaths: List[Path]) -> Set[str]:
        extensions = set(path.suffix for path in contract_filepaths)
        unhandled_extensions = {s for s in extensions - set(self.registered_compilers) if s}
        if len(unhandled_extensions) > 0:
            unhandled_extensions_str = ", ".join(unhandled_extensions)
            raise CompilerError(f"No compiler found for extensions [{unhandled_extensions_str}].")

        return {e for e in extensions if e}
