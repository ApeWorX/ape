from pathlib import Path
from typing import Any, Dict, Iterator, List, Optional, Sequence, Set, Union

from eth_pydantic_types import HexBytes
from ethpm_types import ContractType
from ethpm_types.source import Content

from ape.api import CompilerAPI
from ape.contracts import ContractContainer
from ape.exceptions import CompilerError, ContractLogicError, CustomError
from ape.logging import logger
from ape.managers.base import BaseManager
from ape.utils import log_instead_of_fail
from ape.utils.basemodel import (
    ExtraAttributesMixin,
    ExtraModelAttributes,
    get_attribute_with_extras,
    only_raise_attribute_error,
)
from ape.utils.os import get_full_extension, get_relative_path


class CompilerManager(BaseManager, ExtraAttributesMixin):
    """
    The singleton that manages :class:`~ape.api.compiler.CompilerAPI` instances.
    Each compiler plugin typically contains a single :class:`~ape.api.compiler.CompilerAPI`.

    **NOTE**: Typically, users compile their projects using the CLI via ``ape compile``,
    which uses the :class:`~ape.api.compiler.CompilerAPI` under-the-hood.

    Usage example::

        from ape import compilers  # "compilers" is the CompilerManager singleton
    """

    _registered_compilers_cache: Dict[Path, Dict[str, CompilerAPI]] = {}

    @log_instead_of_fail(default="<CompilerManager>")
    def __repr__(self) -> str:
        num_compilers = len(self.registered_compilers)
        cls_name = getattr(type(self), "__name__", CompilerManager.__name__)
        return f"<{cls_name} len(registered_compilers)={num_compilers}>"

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        yield ExtraModelAttributes(
            name="compilers",
            # Allow referencing compilers by name e.g. `compilers.vyper`.
            attributes=lambda: {c.name: c for c in self.registered_compilers.values()},
        )

    @only_raise_attribute_error
    def __getattr__(self, attr_name: str) -> Any:
        return get_attribute_with_extras(self, attr_name)

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
            self.config_manager.get_config(plugin_name)

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
                return compiler.model_copy(update={"compiler_settings": settings})

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
              file-extension as well as when there are contract-type collisions across compilers.

        Args:
            contract_filepaths (Sequence[Union[pathlib.Path], str]): The files to compile,
              as ``pathlib.Path`` objects or path-strs.
            settings (Optional[Dict]): Adhoc compiler settings. Defaults to None.
              Ensure the compiler name key is present in the dict for it to work.

        Returns:
            Dict[str, ``ContractType``]: A mapping of contract names to their type.
        """
        contract_file_paths = [Path(p) if isinstance(p, str) else p for p in contract_filepaths]
        extensions = self._get_contract_extensions(contract_file_paths)
        contracts_folder = self.config_manager.contracts_folder
        contract_types_dict: Dict[str, ContractType] = {}
        cached_manifest = self.project_manager.local_project.cached_manifest

        # Load past compiled contracts for verifying type-collision and other things.
        already_compiled_contracts: Dict[str, ContractType] = {}
        already_compiled_paths: List[Path] = []
        for name, ct in ((cached_manifest.contract_types or {}) if cached_manifest else {}).items():
            if not ct.source_id:
                continue

            _file = contracts_folder / ct.source_id
            if not _file.is_file():
                continue

            already_compiled_contracts[name] = ct
            already_compiled_paths.append(_file)

        exclusions = self.config_manager.get_config("compile").exclude
        for extension in extensions:
            ignore_path_lists = [contracts_folder.rglob(p) for p in exclusions]
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
                and path not in already_compiled_paths
                and get_full_extension(path) == extension
            ]

            if not paths_to_compile:
                continue

            source_ids = [get_relative_path(p, contracts_folder) for p in paths_to_compile]
            for source_id in source_ids:
                logger.info(f"Compiling '{source_id}'.")

            name = self.registered_compilers[extension].name
            compiler = self.get_compiler(name, settings=settings)
            if compiler is None:
                # For mypy - should not be possible.
                raise ValueError("Compiler should not be None")

            compiled_contracts = compiler.compile(
                paths_to_compile, base_path=self.config_manager.get_config("compile").base_path
            )

            # Validate some things about the compile contracts.
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

                full_ct_dict = {**contract_types_dict, **already_compiled_contracts}
                if contract_name in full_ct_dict:
                    already_added_contract_type = full_ct_dict[contract_name]
                    error_message = (
                        f"{ContractType.__name__} collision between sources "
                        f"'{contract_type.source_id}' and "
                        f"'{already_added_contract_type.source_id}'."
                    )
                    raise CompilerError(error_message)

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
            **kwargs (Any): Additional overrides for the ``ethpm_types.ContractType`` model.

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
                sources = [
                    p for p in contract_filepaths if get_full_extension(p) == ext and p.is_file()
                ]
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
        extensions = {get_full_extension(path) for path in contract_filepaths}
        unhandled_extensions = {s for s in extensions - set(self.registered_compilers) if s}
        if len(unhandled_extensions) > 0:
            unhandled_extensions_str = ", ".join(unhandled_extensions)
            raise CompilerError(f"No compiler found for extensions [{unhandled_extensions_str}].")

        return {e for e in extensions if e}

    def enrich_error(self, err: ContractLogicError) -> ContractLogicError:
        """
        Enrich a contract logic error using compiler information, such
        known PC locations for compiler runtime errors.

        Args:
            err (:class:`~ape.exceptions.ContractLogicError`): The exception
              to enrich.

        Returns:
            :class:`~ape.exceptions.ContractLogicError`: The enriched exception.
        """
        # First, try enriching using their ABI.
        err = self.get_custom_error(err) or err
        if not (contract_type := err.contract_type):
            return err

        # Delegate to compiler APIs.
        elif source_id := contract_type.source_id:
            # Source ID found! Delegate to a CompilerAPI for enrichment.
            ext = get_full_extension(Path(source_id))
            if ext not in self.registered_compilers:
                # Compiler not found.
                return err

            compiler = self.registered_compilers[ext]
            return compiler.enrich_error(err)

        # No further enrichment.
        return err

    def get_custom_error(self, err: ContractLogicError) -> Optional[CustomError]:
        """
        Get a custom error for the given contract logic error using the contract-type
        found from address-data in the error. Returns ``None`` if the given error is
        not a custom-error or it is not able to find the associated contract type or
        address.

        Args:
            err (:class:`~ape.exceptions.ContractLogicError`): The error to enrich
              as a custom error.

        Returns:

        """
        message = err.revert_message
        if not message.startswith("0x"):
            return None
        elif not (address := err.address):
            return None

        if provider := self.network_manager.active_provider:
            ecosystem = provider.network.ecosystem
        else:
            # Default to Ethereum.
            ecosystem = self.network_manager.ethereum

        try:
            return ecosystem.decode_custom_error(
                HexBytes(message),
                address,
                base_err=err.base_err,
                source_traceback=err.source_traceback,
                trace=err.trace,
                txn=err.txn,
            )
        except NotImplementedError:
            return None

    def flatten_contract(self, path: Path, **kwargs) -> Content:
        """
        Get the flattened version of a contract via its source path.
        Delegates to the matching :class:`~ape.api.compilers.CompilerAPI`.

        Args:
            path (``pathlib.Path``): The source path of the contract.

        Returns:
            ``ethpm_types.source.Content``: The flattened contract content.
        """

        ext = get_full_extension(path)
        if ext not in self.registered_compilers:
            raise CompilerError(f"Unable to flatten contract. Missing compiler for '{ext}'.")

        compiler = self.registered_compilers[ext]
        return compiler.flatten_contract(path, **kwargs)

    def can_trace_source(self, filename: str) -> bool:
        """
        Check if Ape is able trace the source lines for the given file.
        Checks that both the compiler is registered and that it supports
        the :meth:`~ape.api.compilers.CompilerAPI.trace_source` API method.

        Args:
            filename (str): The file to check.

        Returns:
            bool: ``True`` when the source is traceable.
        """
        path = Path(filename)
        if not path.is_file():
            return False

        extension = get_full_extension(path)
        if extension in self.registered_compilers:
            compiler = self.registered_compilers[extension]
            if compiler.supports_source_tracing:
                return True

        # We are not able to get coverage for this file.
        return False
