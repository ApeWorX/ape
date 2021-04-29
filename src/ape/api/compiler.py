from abc import ABC, abstractmethod
from pathlib import Path
from typing import List

from ape.types import ContractType


class CompilerAPI(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @property
    @abstractmethod
    def versions(self) -> List[str]:
        # TODO: Does this need the set of all files in a package
        #       to determine the full set of versions?
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
