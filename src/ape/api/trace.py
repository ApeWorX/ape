import sys
from abc import abstractmethod
from collections.abc import Iterator, Sequence
from typing import IO, Any, Optional

from ape.types.trace import ContractFunctionPath, GasReport
from ape.utils.basemodel import BaseInterfaceModel


class TraceAPI(BaseInterfaceModel):
    """
    The class returned from
    :meth:`~ape.api.providers.ProviderAPI.get_transaction_trace`.
    """

    @abstractmethod
    def show(self, verbose: bool = False, file: IO[str] = sys.stdout):
        """
        Show the enriched trace.
        """

    @abstractmethod
    def get_gas_report(
        self, exclude: Optional[Sequence["ContractFunctionPath"]] = None
    ) -> GasReport:
        """
        Get the gas report.
        """

    @abstractmethod
    def show_gas_report(self, verbose: bool = False, file: IO[str] = sys.stdout):
        """
        Show the gas report.
        """

    @property
    @abstractmethod
    def return_value(self) -> Any:
        """
        The return value deduced from the trace.
        """

    @property
    @abstractmethod
    def revert_message(self) -> Optional[str]:
        """
        The revert message deduced from the trace.
        """

    @abstractmethod
    def get_raw_frames(self) -> Iterator[dict]:
        """
        Get raw trace frames for deeper analysis.
        """

    @abstractmethod
    def get_raw_calltree(self) -> dict:
        """
        Get a raw calltree for deeper analysis.
        """
