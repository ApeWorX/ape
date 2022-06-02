from pathlib import Path
from typing import Dict, List, Optional, Set

from ethpm_types import ContractType

from ape.api import CompilerAPI
from ape.exceptions import CompilerError
from ape.logging import logger
from ape.utils import get_relative_path

from .base import BaseManager


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
                source_id = get_relative_path(path, self.config_manager.contracts_folder)
                logger.info(f"Compiling '{source_id}'.")

            compiled_contracts = self.registered_compilers[extension].compile(
                paths_to_compile, base_path=self.config_manager.contracts_folder
            )
            for contract_type in compiled_contracts:

                if contract_type.name in contract_types_dict:
                    raise CompilerError(
                        "ContractType collision across compiler plugins "
                        f"with contract name: {contract_type.name}"
                    )

                contract_types_dict[contract_type.name] = contract_type

        return contract_types_dict  # type: ignore

    def get_imports(
        self, contract_filepaths: List[Path], base_path: Optional[Path]
    ) -> Dict[str, List[str]]:
        """
        Combine import dicts from all compilers, where the key is a contract's source_id
        and the value is a list of import source_ids.

        Args:
            contract_filepaths (List[pathlib.Path]): A list of source file paths to compile.
            base_path (Optional[pathlib.Path]): Optionally provide the base path, such as the
              project ``contracts/`` directory. Defaults to ``None``. When using in a project
              via ``ape compile``, gets set to the project's ``contracts/`` directory.

        Returns:
            Dict[str, List[str]]: A dictionary like ``{source_id: [import_source_id, ...], ...}``
        """
        imports_dict: Dict[str, List[str]] = {}

        for _, compiler in self.registered_compilers.items():
            try:
                imports = compiler.get_imports(
                    contract_filepaths=contract_filepaths, base_path=base_path
                )
            except NotImplementedError:
                imports = None

            if imports:
                imports_dict.update(imports)

        return imports_dict

    def get_references(self, imports_dict: Dict[str, List[str]]) -> Dict[str, List[str]]:
        """
        Provide a mapping containing all referenced source_ids for a given project.
        Each entry contains a source_id as a key and list of source_ids that reference a
        given contract.

        Args:
            imports_dict (Dict[str, List[str]]): A dictionary of source_ids from all compilers.

        Returns:
            Dict[str, List[str]]: A dictionary like ``{source_id: [referring_source_id, ...], ...}``
        """
        references_dict: Dict[str, List[str]] = {}
        if not imports_dict:
            return {}

        for key, imports_list in imports_dict.items():
            for filepath in imports_list:
                if filepath not in references_dict:
                    references_dict[filepath] = []
                references_dict[filepath].append(key)

        return references_dict

    def _get_contract_extensions(self, contract_filepaths: List[Path]) -> Set[str]:
        extensions = set(path.suffix for path in contract_filepaths)
        unhandled_extensions = {s for s in extensions - set(self.registered_compilers) if s}
        if len(unhandled_extensions) > 0:
            unhandled_extensions_str = ", ".join(unhandled_extensions)
            raise CompilerError(f"No compiler found for extensions [{unhandled_extensions_str}].")

        return {e for e in extensions if e}
