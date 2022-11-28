from pathlib import Path
from typing import Dict, List, Optional, Set

from ethpm_types import ContractType
from semantic_version import Version  # type: ignore

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

    @property
    @abstractmethod
    def name(self) -> str:
        ...

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
    def get_imports(  # type: ignore[empty-body]
        self, contract_filepaths: List[Path], base_path: Optional[Path]
    ) -> Dict[str, List[str]]:
        """
        Returns a list of imports as source_ids for each contract's source_id in a given compiler.

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
