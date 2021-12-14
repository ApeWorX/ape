from pathlib import Path
from typing import List, Set

from ape.types import ContractType
from ape.utils import abstractdataclass, abstractmethod

from .config import ConfigItem


@abstractdataclass
class CompilerAPI:
    config: ConfigItem

    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def get_versions(self, all_paths: List[Path]) -> Set[str]:
        """
        Retrieve set of available compiler versions for this plugin to compile `all_paths`
        """

    @abstractmethod
    def compile(self, contract_filepaths: List[Path]) -> List[ContractType]:
        """
        Compile the source given ``pkg_manifest``.
        All compiler plugins must implement this function.
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"

    def __str__(self) -> str:
        return f"{self.name}>"
