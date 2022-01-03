from pathlib import Path
from typing import List, Set

from ape.types import ContractType
from ape.utils import abstractdataclass, abstractmethod

from .config import ConfigItem


@abstractdataclass
class CompilerAPI:
    """
    Compiler plugins, such as for languages like
    `Solidity <https://docs.soliditylang.org/en/v0.8.11/>`__ or
    `Vyper <https://vyper.readthedocs.io/en/stable/>`__, implement this API.
    See the repository for the `ape-solidity <https://github.com/ApeWorX/ape-solidity>`__ plugin or
    the `ape-vyper <https://github.com/ApeWorX/ape-vyper>`__ plugin as example implementations of
    this API.
    """

    config: ConfigItem
    """The :class:`ape.api.config.ConfigItem` for this compiler plugin."""

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
    def compile(self, contract_filepaths: List[Path]) -> List[ContractType]:
        """
        Compile the given source files. All compiler plugins must implement this function.

        Args:
            contract_filepaths (List[pathlib.Path]): A list of source file paths to compile.

        Returns:
            List[:class:`~ape.type.contract.ContractType`]
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"

    def __str__(self) -> str:
        return self.name
