from abc import ABC, abstractmethod
from pathlib import Path

from ape.types import ContractType


class CompilerAPI(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @abstractmethod
    def compile(self, contract_filepath: Path) -> ContractType:
        """
        Compile the source given `pkg_manifest`.
        All compiler plugins must implement this function.
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"

    def __str__(self) -> str:
        return f"{self.name}>"
