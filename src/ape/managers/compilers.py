from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Set, Union

from ethpm_types import ContractType
from ethpm_types.source import Content

from ape.api import CompilerAPI
from ape.contracts import ContractContainer
from ape.exceptions import ApeAttributeError, CompilerError, ContractLogicError
from ape.logging import logger
from ape.managers.base import BaseManager
from ape.utils import get_relative_path


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

    def __getattr__(self, name: str) -> Any:
        try:
            return self.__getattribute__(name)
        except AttributeError:
            pass

        if compiler := self.get_compiler(name):
            return compiler

        raise ApeAttributeError(f"No attribute or compiler named '{name}'.")

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

    def get_compiler(self, name: str, settings: Optional[Dict] = None) -> Optional[CompilerAPI]:
        for compiler in self.registered_compilers.values():
            if compiler.name != name:
                continue

            if settings is not None and settings != compiler.compiler_settings:
                # Use a new instance to support multiple compilers of same type.
                return compiler.copy(update={"compiler_settings": settings})

            return compiler

        return None

    def compile(
        self, contract_filepaths: Sequence[Union[Path, str]], settings: Optional[Dict] = None
    ) -> Dict[str, ContractType]:
        """
        Invoke :meth:`ape.ape.compiler.CompilerAPI.compile` for each of the given files.
        For example, use the `ape-solidity plugin <https://github.com/ApeWorX/ape-solidity>`__
        to compile ``'.sol'`` files.

        Raises:
            :class:`~ape.exceptions.CompilerError`: When there is no compiler found for the given
              extension as well as when there is a contract-type collision across compilers.

        Args:
            contract_filepaths (Sequence[Union[pathlib.Path], str]): The list of files to compile,
              as ``pathlib.Path`` objects. You can also pass a list of `str` that will
              automatically get turned to ``pathlib.Path`` objects.
            settings (Optional[Dict]): Adhoc compiler settings. Defaults to None.
              Ensure the compiler name key is present in the dict for it to work.

        Returns:
            Dict[str, ``ContractType``]: A mapping of contract names to their type.
        """
        contract_file_paths = [Path(p) if isinstance(p, str) else p for p in contract_filepaths]
        extensions = self._get_contract_extensions(contract_file_paths)
        contracts_folder = self.config_manager.contracts_folder
        contract_types_dict: Dict[str, ContractType] = {}
        built_paths = [p for p in self.project_manager.local_project._cache_folder.glob("*.json")]
        built_names = [p.stem for p in built_paths if p.stem != "__local__"]

        for extension in extensions:
            path_patterns_to_ignore = self.config_manager.compiler.ignore_files
            ignore_path_lists = [contracts_folder.rglob(p) for p in path_patterns_to_ignore]
            paths_to_ignore = [
                contracts_folder / get_relative_path(p, contracts_folder)
                for files in ignore_path_lists
                for p in files
            ]

            # Filter out in-source cache files from dependencies.
            paths_to_compile = [
                path
                for path in contract_file_paths
                if path.is_file()
                and path not in paths_to_ignore
                and path not in built_paths
                and path.suffix == extension
                and not any(x in [p.name for p in path.parents] for x in (".cache", ".build"))
            ]

            source_ids = [get_relative_path(p, contracts_folder) for p in paths_to_compile]
            for source_id in source_ids:
                logger.info(f"Compiling '{source_id}'.")

            name = self.registered_compilers[extension].name
            compiler = self.get_compiler(name, settings=settings)
            if compiler is None:
                # For mypy - should not be possible.
                raise ValueError("Compiler should not be None")

            compiled_contracts = compiler.compile(paths_to_compile, base_path=contracts_folder)

            for contract_type in compiled_contracts:
                contract_name = contract_type.name
                if not contract_name:
                    # Compiler plugins should have let this happen, but just in case we get here,
                    # raise a better error so the user has some indication of what happened.
                    if contract_type.source_id:
                        raise CompilerError(
                            f"Contract '{contract_type.source_id}' missing name. "
                            f"Was compiler plugin for '{extension} implemented correctly?"
                        )
                    else:
                        raise CompilerError(
                            f"Empty contract type found in compiler '{extension}'. "
                            f"Was compiler plugin for '{extension} implemented correctly?"
                        )

                if contract_name in contract_types_dict:
                    already_added_contract_type = contract_types_dict[contract_name]
                    error_message = (
                        f"{ContractType.__name__} collision between sources "
                        f"'{contract_type.source_id}' and "
                        f"'{already_added_contract_type.source_id}'."
                    )
                    raise CompilerError(error_message)

                elif contract_name in built_names:
                    # Ensure we are not colliding.
                    existing_artifact = (
                        self.project_manager.local_project._cache_folder / f"{contract_name}.json"
                    )

                    try:
                        existing_contract = ContractType.parse_file(existing_artifact)
                    except Exception:
                        existing_artifact.unlink()

                    else:
                        if existing_contract.source_id:
                            path = self.project_manager.lookup_path(existing_contract.source_id)
                            if path and existing_contract.source_id != contract_type.source_id:
                                error_message = (
                                    f"{ContractType.__name__} collision '{contract_name}'."
                                )
                                raise CompilerError(error_message)

                            elif not path:
                                # Artifact remaining from deleted contract, can delete.
                                existing_artifact.unlink()

                contract_types_dict[contract_name] = contract_type

        return contract_types_dict

    def compile_source(
        self,
        compiler_name: str,
        code: str,
        settings: Optional[Dict] = None,
        **kwargs,
    ) -> ContractContainer:
        """
        Compile the given program.

        Usage example::

            code = '[{"name":"foo","type":"fallback", "stateMutability":"nonpayable"}]'
            contract_type = compilers.compile_source(
                "ethpm",
                code,
                contractName="MyContract",
            )

        Args:
            compiler_name (str): The name of the compiler to use.
            code (str): The source code to compile.
            settings (Optional[Dict]): Compiler settings.
            **kwargs: Additional overrides for the ``ethpm_types.ContractType`` model.

        Returns:
            ``ContractContainer``: A contract container ready to be deployed.
        """
        compiler = self.get_compiler(compiler_name, settings=settings)
        if not compiler:
            raise ValueError(f"Compiler '{compiler_name}' not found.")

        contract_type = compiler.compile_code(
            code,
            base_path=self.project_manager.contracts_folder,
            **kwargs,
        )
        return ContractContainer(contract_type=contract_type)

    def get_imports(
        self, contract_filepaths: Sequence[Path], base_path: Optional[Path] = None
    ) -> Dict[str, List[str]]:
        """
        Combine import dicts from all compilers, where the key is a contract's source_id
        and the value is a list of import source_ids.

        Args:
            contract_filepaths (Sequence[pathlib.Path]): A list of source file paths to compile.
            base_path (Optional[pathlib.Path]): Optionally provide the base path, such as the
              project ``contracts/`` directory. Defaults to ``None``. When using in a project
              via ``ape compile``, gets set to the project's ``contracts/`` directory.

        Returns:
            Dict[str, List[str]]: A dictionary like ``{source_id: [import_source_id, ...], ...}``
        """
        imports_dict: Dict[str, List[str]] = {}
        base_path = base_path or self.project_manager.contracts_folder

        for ext, compiler in self.registered_compilers.items():
            try:
                sources = [p for p in contract_filepaths if p.suffix == ext and p.is_file()]
                imports = compiler.get_imports(contract_filepaths=sources, base_path=base_path)
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
        extensions = {path.suffix for path in contract_filepaths}
        unhandled_extensions = {s for s in extensions - set(self.registered_compilers) if s}
        if len(unhandled_extensions) > 0:
            unhandled_extensions_str = ", ".join(unhandled_extensions)
            raise CompilerError(f"No compiler found for extensions [{unhandled_extensions_str}].")

        return {e for e in extensions if e}

    def enrich_error(self, err: ContractLogicError) -> ContractLogicError:
        """
        Enrich a contract logic error using compiler information, such
        known PC locations for compiler runtime errors, such as math errors.

        Args:
            err (:class:`~ape.exceptions.ContractLogicError`): The exception
              to enrich.

        Returns:
            :class:`~ape.exceptions.ContractLogicError`: The enriched exception.
        """

        address = err.address
        if not address:
            # Contract address not found.
            return err

        try:
            contract = self.chain_manager.contracts.get(address)
        except RecursionError:
            contract = None

        if not contract or not contract.source_id:
            # Contract or source not found.
            return err

        ext = Path(contract.source_id).suffix
        if ext not in self.registered_compilers:
            # Compiler not found.
            return err

        compiler = self.registered_compilers[ext]
        return compiler.enrich_error(err)

    def flatten_contract(self, path: Path) -> Content:
        """
        Get the flattened version of a contract via its source path.
        Delegates to the matching :class:`~ape.api.compilers.CompilerAPI`.

        Args:
            path (``pathlib.Path``): The source path of the contract.

        Returns:
            ``ethpm_types.source.Content``: The flattened contract content.
        """

        if path.suffix not in self.registered_compilers:
            raise CompilerError(
                f"Unable to flatten contract. Missing compiler for '{path.suffix}'."
            )

        compiler = self.registered_compilers[path.suffix]
        return compiler.flatten_contract(path)

    def can_trace_source(self, filename: str) -> bool:
        """
        Check if Ape is able trace the source lines for the given file.
        Checks that both the compiler is registered and that it supports
        the :meth:`~ape.api.compilers.CompilerAPI.trace_source` API method.

        Args:
            filename (str): The file to check.

        Returns:
            bool
        """
        path = Path(filename)
        if not path.is_file():
            return False

        extension = path.suffix
        if extension in self.registered_compilers:
            compiler = self.registered_compilers[extension]
            if compiler.supports_source_tracing:
                return True

        # We are not able to get coverage for this file.
        return False
