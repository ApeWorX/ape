from functools import cached_property
from pathlib import Path
from typing import Dict, Iterator, List, Optional, Set, Tuple

from ethpm_types import ContractType, HexBytes
from ethpm_types.source import Content, ContractSource
from evm_trace.geth import TraceFrame as EvmTraceFrame
from evm_trace.geth import create_call_node_data
from semantic_version import Version  # type: ignore

from ape.api.config import PluginConfig
from ape.exceptions import APINotImplementedError, ContractLogicError
from ape.types.coverage import ContractSourceCoverage
from ape.types.trace import SourceTraceback, TraceFrame
from ape.utils import BaseInterfaceModel, abstractmethod, raises_not_implemented


class CompilerAPI(BaseInterfaceModel):
    """
    Compiler plugins, such as for languages like
    `Solidity <https://docs.soliditylang.org/en/v0.8.11/>`__ or
    `Vyper <https://vyper.readthedocs.io/en/stable/>`__, implement this API.

    See the repository for the `ape-solidity <https://github.com/ApeWorX/ape-solidity>`__ plugin or
    the `ape-vyper <https://github.com/ApeWorX/ape-vyper>`__ plugin as example implementations of
    this API.
    """

    compiler_settings: Dict = {}
    """
    Adhoc compiler settings.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        ...

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
        data = {**self.config.dict(), **self.compiler_settings}
        return CustomConfig.parse_obj(data)

    @abstractmethod
    def get_versions(self, all_paths: List[Path]) -> Set[str]:
        """
        Retrieve the set of available compiler versions for this plugin to compile ``all_paths``.

        Args:
            all_paths (List[pathlib.Path]): The list of paths.

        Returns:
            Set[str]: A set of available compiler versions.
        """

    @raises_not_implemented
    def get_compiler_settings(  # type: ignore[empty-body]
        self, contract_filepaths: List[Path], base_path: Optional[Path] = None
    ) -> Dict[Version, Dict]:
        """
        Get a mapping of the settings that would be used to compile each of the sources
        by the compiler version number.

        Args:
            contract_filepaths (List[pathlib.Path]): The list of paths.
            base_path (Optional[pathlib.Path]): The contracts folder base path.

        Returns:
            Dict[Version, Dict]: A dict of compiler settings by compiler version.
        """

    @abstractmethod
    def compile(
        self, contract_filepaths: List[Path], base_path: Optional[Path]
    ) -> List[ContractType]:
        """
        Compile the given source files. All compiler plugins must implement this function.

        Args:
            contract_filepaths (List[pathlib.Path]): A list of source file paths to compile.
            base_path (Optional[pathlib.Path]): Optionally provide the base path, such as the
              project ``contracts/`` directory. Defaults to ``None``. When using in a project
              via ``ape compile``, gets set to the project's ``contracts/`` directory.

        Returns:
            List[:class:`~ape.type.contract.ContractType`]
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
        self, contract_filepaths: List[Path], base_path: Optional[Path]
    ) -> Dict[str, List[str]]:
        """
        Returns a list of imports as source_ids for each contract's source_id in a given
        compiler.

        Args:
            contract_filepaths (List[pathlib.Path]): A list of source file paths to compile.
            base_path (Optional[pathlib.Path]): Optionally provide the base path, such as the
              project ``contracts/`` directory. Defaults to ``None``. When using in a project
              via ``ape compile``, gets set to the project's ``contracts/`` directory.

        Returns:
            Dict[str, List[str]]: A dictionary like ``{source_id: [import_source_id, ...], ...}``
        """

    @raises_not_implemented
    def get_version_map(  # type: ignore[empty-body]
        self,
        contract_filepaths: List[Path],
        base_path: Optional[Path] = None,
    ) -> Dict[Version, Set[Path]]:
        """
        Get a map of versions to source paths.

        Args:
            contract_filepaths (List[Path]): Input source paths. Defaults to all source paths
              per compiler.
            base_path (Path): The base path of sources. Defaults to the project's
              ``contracts_folder``.

        Returns:
            Dict[Version, Set[Path]]
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"

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
        Enrich a contract logic error using compiler information, such
        known PC locations for compiler runtime errors, such as math errors.

        Args:
            err (:class:`~ape.exceptions.ContractLogicError`): The exception
              to enrich.

        Returns:
            :class:`~ape.exceptions.ContractLogicError`: The enriched exception.
        """

        return err

    @raises_not_implemented
    def trace_source(  # type: ignore[empty-body]
        self, contract_type: ContractType, trace: Iterator[TraceFrame], calldata: HexBytes
    ) -> SourceTraceback:
        """
        Get a source-traceback for the given contract type.
        The source traceback object contains all the control paths taken in the transaction.
        When available, source-code location information is accessible from the object.

        Args:
            contract_type (``ContractType``): A contract type that was created by this compiler.
            trace (Iterator[:class:`~ape.types.trace.TraceFrame`]): The resulting frames from
              executing a function defined in the given contract type.
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
            **kwargs: Additional compiler-specific settings. See specific
              compiler plugins when applicable.

        Returns:
            ``ethpm_types.source.Content``: The flattened contract content.
        """

    def _create_contract_from_call(
        self, frame: TraceFrame
    ) -> Tuple[Optional[ContractSource], HexBytes]:
        evm_frame = EvmTraceFrame(**frame.raw)
        data = create_call_node_data(evm_frame)
        calldata = data.get("calldata", HexBytes(""))
        if not (address := (data.get("address", frame.contract_address) or None)):
            return None, calldata

        try:
            address = self.provider.network.ecosystem.decode_address(address)
        except Exception:
            return None, calldata

        if address not in self.chain_manager.contracts:
            return None, calldata

        called_contract = self.chain_manager.contracts[address]
        return self.project_manager._create_contract_source(called_contract), calldata

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
