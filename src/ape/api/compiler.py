from abc import ABC, abstractmethod

from ape.package import PackageManifest


class CompilerAPI(ABC):
    @property
    @abstractmethod
    def name(self) -> str:
        ...

    @classmethod
    @abstractmethod
    def handles(self, contract_type: str) -> bool:
        ...

    @abstractmethod
    def compile(self, pkg_manifest: PackageManifest) -> PackageManifest:
        """
        Compile the source given `pkg_manifest`.
        All compiler plugins must implement this function.
        """

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.name}>"

    def __str__(self) -> str:
        return f"{self.name}>"
