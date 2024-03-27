from collections import defaultdict
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterable, Iterator, List, Optional, Sequence, Union

from ethpm_types import ContractType
from ethpm_types.source import Content

from ape.api.compiler import CompilerAPI
from ape.contracts import ContractContainer
from ape.exceptions import CompilerError, ContractLogicError
from ape.logging import logger
from ape.managers.base import BaseManager
from ape.utils.basemodel import (
    ExtraAttributesMixin,
    ExtraModelAttributes,
    get_attribute_with_extras,
)
from ape.utils.os import get_full_extension

if TYPE_CHECKING:
    from ape.managers.project import ProjectManager


class CompilerManager(BaseManager, ExtraAttributesMixin):
    """
    The singleton that manages :class:`~ape.api.compiler.CompilerAPI` instances.
    Each compiler plugin typically contains a single :class:`~ape.api.compiler.CompilerAPI`.

    **NOTE**: Typically, users compile their projects using the CLI via ``ape compile``,
    which uses the :class:`~ape.api.compiler.CompilerAPI` under-the-hood.

    Usage example::

        from ape import compilers  # "compilers" is the CompilerManager singleton
    """

    def __repr__(self):
        ext_str = ""
        try:
            cls_name = getattr(type(self), "__name__", CompilerManager.__name__)
            if compilers := self.registered_compilers:
                ext_str = f" {','.join(compilers)}"

        except Exception:
            # Prevents errors from happening in repr.
            cls_name = CompilerManager.__name__

        return f"<{cls_name} '{ext_str}'>"

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        yield ExtraModelAttributes(
            name="compilers",
            # Allow referencing compilers by name e.g. `compilers.vyper`.
            attributes=lambda: {c.name: c for c in self.registered_compilers.values()},
        )

    def __getattr__(self, attr_name: str) -> Any:
        return get_attribute_with_extras(self, attr_name)

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
            self.config_manager.get_config(plugin_name)
            compiler = compiler_class()

            for extension in extensions:
                if extension not in registered_compilers:
                    registered_compilers[extension] = compiler

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
        self,
        contract_filepaths: Iterable[Union[Path, str]],
        project: Optional["ProjectManager"] = None,
        settings: Optional[Dict] = None,
    ) -> Iterator[ContractType]:
        """
        Invoke :meth:`ape.ape.compiler.CompilerAPI.compile` for each of the given files.
        For example, use the `ape-solidity plugin <https://github.com/ApeWorX/ape-solidity>`__
        to compile ``'.sol'`` files.

        Raises:
            :class:`~ape.exceptions.CompilerError`: When there is no compiler found for the given
              file-extension as well as when there are contract-type collisions across compilers.

        Args:
            contract_filepaths (Iterable[Union[pathlib.Path], str]): The files to compile,
              as ``pathlib.Path`` objects or path-strs.
            project (Optional[:class:`~ape.managers.project.ProjectManager`]): Optionally
              compile a different project that the one from the current-working directory.
            settings (Optional[Dict]): Adhoc compiler settings. Defaults to None.
              Ensure the compiler name key is present in the dict for it to work.

        Returns:
            Iterator[``ContractType``]: An iterator of contract types.
        """
        pm = project or self.project_manager
        files_by_ext = defaultdict(list)
        for path in map(Path, contract_filepaths):
            suffix = get_full_extension(path)
            if suffix in self.registered_compilers:
                files_by_ext[suffix].append(path)

        errors = []
        tracker: Dict[str, str] = {}

        for next_ext, path_set in files_by_ext.items():
            compiler = self.registered_compilers[next_ext]
            try:
                for contract in compiler.compile(path_set, project=pm, settings=settings):
                    if contract.name in tracker:
                        raise CompilerError(
                            f"ContractType collision. "
                            f"Contracts '{tracker[contract.name]}' and '{contract.source_id}' "
                            f"share the name '{contract.name}'."
                        )

                    if contract.name and contract.source_id:
                        tracker[contract.name] = contract.source_id
                        yield contract

            except Exception as err:
                # One of the compilers failed. Show the error but carry on.
                logger.log_debug_stack_trace()
                errors.append(err)
                continue

        if errors:
            raise CompilerError(", ".join([f"{str(e)}" for e in errors])) from errors[0]

    def compile_source(
        self,
        compiler_name: str,
        code: str,
        base_path: Optional[Path] = None,
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
            base_path (Optional[Path]): Contracts base path.
            settings (Optional[Dict]): Compiler settings.
            **kwargs (Any): Additional overrides for the ``ethpm_types.ContractType`` model.

        Returns:
            ``ContractContainer``: A contract container ready to be deployed.
        """
        compiler = self.get_compiler(compiler_name, settings=settings)
        if not compiler:
            raise ValueError(f"Compiler '{compiler_name}' not found.")

        contract_type = compiler.compile_code(code, base_path=base_path, **kwargs)
        return ContractContainer(contract_type=contract_type)

    def get_imports(
        self,
        contract_filepaths: Sequence[Path],
        project: Optional["ProjectManager"] = None,
    ) -> Dict[str, List[str]]:
        """
        Combine import dicts from all compilers, where the key is a contract's source_id
        and the value is a list of import source_ids.

        Args:
            contract_filepaths (Sequence[pathlib.Path]): A list of source file paths to compile.
            project (Optional[:class:`~ape.managers.project.ProjectManager`]): Optionally provide
              the project.

        Returns:
            Dict[str, List[str]]: A dictionary like ``{source_id: [import_source_id, ...], ...}``
        """
        imports_dict: Dict[str, List[str]] = {}

        for ext, compiler in self.registered_compilers.items():
            try:
                sources = [
                    p for p in contract_filepaths if get_full_extension(p) == ext and p.is_file()
                ]
                imports = compiler.get_imports(contract_filepaths=sources, project=project)
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

        ext = get_full_extension(Path(contract.source_id))
        if ext not in self.registered_compilers:
            # Compiler not found.
            return err

        compiler = self.registered_compilers[ext]
        return compiler.enrich_error(err)

    def flatten_contract(self, path: Path, **kwargs) -> Content:
        """
        Get the flattened version of a contract via its source path.
        Delegates to the matching :class:`~ape.api.compilers.CompilerAPI`.

        Args:
            path (``pathlib.Path``): The source path of the contract.

        Returns:
            ``ethpm_types.source.Content``: The flattened contract content.
        """

        suffix = get_full_extension(path)
        if suffix not in self.registered_compilers:
            raise CompilerError(f"Unable to flatten contract. Missing compiler for '{suffix}'.")

        compiler = self.registered_compilers[suffix]
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
