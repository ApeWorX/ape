from collections.abc import Sequence
from functools import cached_property
from pathlib import Path
from typing import Optional

from eth_pydantic_types import HexBytes
from ethpm_types import ContractType
from ethpm_types.source import Content, ContractSource
from packaging.version import Version

from ape.api.config import PluginConfig
from ape.api.trace import TraceAPI
from ape.exceptions import APINotImplementedError, ContractLogicError
from ape.types.coverage import ContractSourceCoverage
from ape.types.trace import SourceTraceback
from ape.utils import (
    BaseInterfaceModel,
    abstractmethod,
    log_instead_of_fail,
    raises_not_implemented,
)


class CompilerAPI(BaseInterfaceModel):
    """
    Compiler plugins, such as for languages like
    `Solidity <https://docs.soliditylang.org/en/v0.8.11/>`__ or
    `Vyper <https://vyper.readthedocs.io/en/stable/>`__, implement this API.

    See the repository for the `ape-solidity <https://github.com/ApeWorX/ape-solidity>`__ plugin or
    the `ape-vyper <https://github.com/ApeWorX/ape-vyper>`__ plugin as example implementations of
    this API.
    """

    compiler_settings: dict = {}
    """
    Adhoc compiler settings.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """
        The name of the compiler.
        """

    @property
    def config(self) -> PluginConfig:
        """
        The provider's configuration.
        """
        return self.config_manager.get_config(self.name)

    @property
    def settings(self) -> PluginConfig:
        """
        The combination of settings from ``ape-config.yaml`` and ``.compiler_settings``.
        """
        CustomConfig = self.config.__class__
        data = {**self.config.model_dump(by_alias=True), **self.compiler_settings}
        return CustomConfig.model_validate(data)

    @abstractmethod
    def get_versions(self, all_paths: Sequence[Path]) -> set[str]:
        """
        Retrieve the set of available compiler versions for this plugin to compile ``all_paths``.

        Args:
            all_paths (Sequence[pathlib.Path]): The list of paths.

        Returns:
            set[str]: A set of available compiler versions.
        """

    @raises_not_implemented
    def get_compiler_settings(  # type: ignore[empty-body]
        self, contract_filepaths: Sequence[Path], base_path: Optional[Path] = None
    ) -> dict[Version, dict]:
        """
        Get a mapping of the settings that would be used to compile each of the sources
        by the compiler version number.

        Args:
            contract_filepaths (Sequence[pathlib.Path]): The list of paths.
            base_path (Optional[pathlib.Path]): The contracts folder base path.

        Returns:
            dict[Version, dict]: A dict of compiler settings by compiler version.
        """

    @abstractmethod
    def compile(
        self, contract_filepaths: Sequence[Path], base_path: Optional[Path]
    ) -> list[ContractType]:
        """
        Compile the given source files. All compiler plugins must implement this function.

        Args:
            contract_filepaths (Sequence[pathlib.Path]): A list of source file paths to compile.
            base_path (Optional[pathlib.Path]): Optionally provide the base path, such as the
              project ``contracts/`` directory. Defaults to ``None``. When using in a project
              via ``ape compile``, gets set to the project's ``contracts/`` directory.

        Returns:
            list[:class:`~ape.type.contract.ContractType`]
        """

    @raises_not_implemented
    def compile_code(  # type: ignore[empty-body]
        self,
        code: str,
        base_path: Optional[Path] = None,
        **kwargs,
    ) -> ContractType:
        """
        Compile a program.

        Args:
            code (str): The code to compile.
            base_path (Optional[pathlib.Path]): Optionally provide the base path, such as the
              project ``contracts/`` directory. Defaults to ``None``. When using in a project
              via ``compilers.compile_source()``, gets set to the project's ``contracts/``
              directory.
            **kwargs: Additional overrides for the ``ethpm_types.ContractType`` model.

        Returns:
            ``ContractType``: A compiled contract artifact.
        """

    @raises_not_implemented
    def get_imports(  # type: ignore[empty-body]
        self, contract_filepaths: Sequence[Path], base_path: Optional[Path]
    ) -> dict[str, list[str]]:
        """
        Returns a list of imports as source_ids for each contract's source_id in a given
        compiler.

        Args:
            contract_filepaths (Sequence[pathlib.Path]): A list of source file paths to compile.
            base_path (Optional[pathlib.Path]): Optionally provide the base path, such as the
              project ``contracts/`` directory. Defaults to ``None``. When using in a project
              via ``ape compile``, gets set to the project's ``contracts/`` directory.

        Returns:
            dict[str, list[str]]: A dictionary like ``{source_id: [import_source_id, ...], ...}``
        """

    @raises_not_implemented
    def get_version_map(  # type: ignore[empty-body]
        self,
        contract_filepaths: Sequence[Path],
        base_path: Optional[Path] = None,
    ) -> dict[Version, set[Path]]:
        """
        Get a map of versions to source paths.

        Args:
            contract_filepaths (Sequence[Path]): Input source paths. Defaults to all source paths
              per compiler.
            base_path (Path): The base path of sources. Defaults to the project's
              ``contracts_folder``.

        Returns:
            dict[Version, set[Path]]
        """

    @log_instead_of_fail(default="<CompilerAPI>")
    def __repr__(self) -> str:
        cls_name = getattr(type(self), "__name__", CompilerAPI.__name__)
        return f"<{cls_name} {self.name}>"

    def __str__(self) -> str:
        return self.name

    @cached_property
    def supports_source_tracing(self) -> bool:
        """
        Returns ``True`` if this compiler is able to provider a source
        traceback for a given trace.
        """
        try:
            self.trace_source(None, None, None)  # type: ignore
        except APINotImplementedError:
            return False
        except Exception:
            # Task failed successfully.
            return True

        return True

    def enrich_error(self, err: ContractLogicError) -> ContractLogicError:
        """
        Enrich a contract logic error using compiler information, such as
        known PC locations for compiler runtime errors.

        Args:
            err (:class:`~ape.exceptions.ContractLogicError`): The exception
              to enrich.

        Returns:
            :class:`~ape.exceptions.ContractLogicError`: The enriched exception.
        """

        return err

    @raises_not_implemented
    def trace_source(  # type: ignore[empty-body]
        self, contract_source: ContractSource, trace: TraceAPI, calldata: HexBytes
    ) -> SourceTraceback:
        """
        Get a source-traceback for the given contract type.
        The source traceback object contains all the control paths taken in the transaction.
        When available, source-code location information is accessible from the object.

        Args:
            contract_source (``ContractSource``): A contract type with a local-source that was
              compiled by this compiler.
            trace (:class:`~ape.api.trace.TraceAPI`]): The resulting trace from executing a
              function defined in the given contract type.
            calldata (``HexBytes``): Calldata passed to the top-level call.

        Returns:
            :class:`~ape.types.trace.SourceTraceback`
        """

    @raises_not_implemented
    def flatten_contract(self, path: Path, **kwargs) -> Content:  # type: ignore[empty-body]
        """
        Get the content of a flattened contract via its source path.
        Plugin implementations handle import resolution, SPDX de-duplication,
        and anything else needed.

        Args:
            path (``pathlib.Path``): The source path of the contract.
            **kwargs (Any): Additional compiler-specific settings. See specific
              compiler plugins when applicable.

        Returns:
            ``ethpm_types.source.Content``: The flattened contract content.
        """

    @raises_not_implemented
    def init_coverage_profile(
        self, source_coverage: ContractSourceCoverage, contract_source: ContractSource
    ):  # type: ignore[empty-body]
        """
        Initialize an empty report for the given source ID. Modifies the given source
        coverage in-place.

        Args:
            source_coverage (:class:`~ape.types.coverage.SourceCoverage`): The source
              to generate an empty coverage profile for.
            contract_source (``ethpm_types.source.ContractSource``): The contract with
              source content.
        """
