from pathlib import Path
from typing import List, Set

from ape.types import ContractType

from .base import abstractdataclass, abstractmethod


@abstractdataclass
class CompilerAPI:
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def get_versions(self, all_paths: List[Path]) -> Set[str]:
        ...

    @abstractmethod
    def compile(self, contract_filepaths: List[Path]) -> List[ContractType]:
        """
        Compile the source given `pkg_manifest`.
        All compiler plugins must implement this function.
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"

    def __str__(self) -> str:
        return f"{self.name}>"
