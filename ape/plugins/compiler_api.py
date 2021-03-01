from abc import ABC, abstractmethod
from typing import Dict
from pathlib import Path


class CompilerAPI(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    # TODO move to cls method so instantiation isn't required
    @classmethod
    @abstractmethod
    def extension(self) -> str:
        ...

    # CompilerAPI.compile() -> BuildData
    @abstractmethod
    def compile(self, contracts_folder: Path) -> Dict:
        """
        Compile the source given `contracts_folder`.
        All compiler plugins must implement this function.
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"

    def __str__(self) -> str:
        return f"{self.name}>"
