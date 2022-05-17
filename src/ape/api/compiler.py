from pathlib import Path
from typing import Dict, List, Optional, Set

from ethpm_types import ContractType

from ape.utils import BaseInterfaceModel, abstractmethod, get_relative_path, raises_not_implemented


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
    def get_imports(
        self, contract_filepaths: List[Path], base_path: Optional[Path]
    ) -> Dict[str, List[str]]:
        """
        Returns a list of imports for each contract in a given compiler.

        Args:
            contract_filepaths (List[pathlib.Path]): A list of source file paths to compile.
            base_path (Optional[pathlib.Path]): Optionally provide the base path, such as the
              project ``contracts/`` directory. Defaults to ``None``. When using in a project
              via ``ape compile``, gets set to the project's ``contracts/`` directory.

        Returns:
            Dict[str, List[str]]
        """

    def _get_filename_dict_from_paths(
        self, paths: List[Path], base_path: Optional[Path]
    ) -> Dict[str, List[str]]:
        """
        Structure for getting a list of paths related to a filename.
        Used to create a broad/generous assumption of related paths for a filename.
        """
        filename_dict: Dict[str, List[str]] = {}

        for p in paths:
            filename = str(p).split("/")[-1]

            if not filename_dict.get(filename):
                filename_dict[filename] = []

            if base_path:
                p = get_relative_path(p, base_path)

            filename_dict[filename].append(str(p))

        return filename_dict

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"

    def __str__(self) -> str:
        return self.name
