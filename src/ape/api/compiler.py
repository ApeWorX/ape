from pathlib import Path
from typing import List, Set

from ape.types import ContractType
from ape.utils import abstractdataclass, abstractmethod

from .config import ConfigItem


@abstractdataclass
class CompilerAPI:
    """
    Compiler plugins, such as for languages like Solidity or Vyper, implement this API.
    """

    config: ConfigItem

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def get_versions(self, all_paths: List[Path]) -> Set[str]:
        """
        Retrieve the set of available compiler versions for this plugin to compile ``all_paths``.

        Args:
            all_paths (list[pathlib.Path]): The list of paths.

        Returns:
            set[str]: A set of available compiler versions.
        """

    @abstractmethod
    def compile(self, contract_filepaths: List[Path]) -> List[ContractType]:
        """
        Compile the source given ``pkg_manifest``.
        All compiler plugins must implement this function.

        Args:
            contract_filepaths (list[pathlib.Path]): A list of source file paths to compile.

        Returns:
            list[:class:`~ape.type.contract.ContractType`]
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"

    def __str__(self) -> str:
        return self.name
