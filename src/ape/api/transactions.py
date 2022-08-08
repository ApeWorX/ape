import sys
import time
from typing import IO, TYPE_CHECKING, Iterator, List, Optional, Union

from ethpm_types import HexBytes
from ethpm_types.abi import EventABI
from evm_trace import TraceFrame
from pydantic.fields import Field
from tqdm import tqdm  # type: ignore

from ape.api.explorers import ExplorerAPI
from ape.exceptions import TransactionError
from ape.logging import logger
from ape.types import ContractLog, TransactionSignature
from ape.utils import BaseInterfaceModel, abstractmethod, raises_not_implemented

if TYPE_CHECKING:
    from ape.contracts import ContractEvent


class TransactionAPI(BaseInterfaceModel):
    """
    An API class representing a transaction.
    Ecosystem plugins implement one or more of transaction APIs
    depending on which schemas they permit,
    such as typed-transactions from `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__.
    """

    chain_id: int = Field(0, alias="chainId")
    receiver: Optional[str] = Field(None, alias="to")
    sender: Optional[str] = Field(None, alias="from")
    gas_limit: Optional[int] = Field(None, alias="gas")
    nonce: Optional[int] = None  # NOTE: `Optional` only to denote using default behavior
    value: int = 0
    data: bytes = b""
    type: Union[int, bytes, str]
    max_fee: Optional[int] = None
    max_priority_fee: Optional[int] = None

    # If left as None, will get set to the network's default required confirmations.
    required_confirmations: Optional[int] = Field(None, exclude=True)

    signature: Optional[TransactionSignature] = Field(exclude=True)

    class Config:
        allow_population_by_field_name = True

    @property
    def total_transfer_value(self) -> int:
        """
        The total amount of WEI that a transaction could use.
        Useful for determining if an account balance can afford
        to submit the transaction.
        """
        if self.max_fee is None:
            raise TransactionError(message="Max fee must not be null.")

        return self.value + self.max_fee

    @property
    @abstractmethod
    def txn_hash(self) -> HexBytes:
        """
        The calculated hash of the transaction.
        """

    @abstractmethod
    def serialize_transaction(self) -> bytes:
        """
        Serialize the transaction
        """

    def __repr__(self) -> str:
        data = self.dict()
        params = ", ".join(f"{k}={v}" for k, v in data.items())
        return f"<{self.__class__.__name__} {params}>"

    def __str__(self) -> str:
        data = self.dict()
        if len(data["data"]) > 9:
            data["data"] = (
                "0x" + bytes(data["data"][:3]).hex() + "..." + bytes(data["data"][-3:]).hex()
            )
        else:
            data["data"] = "0x" + bytes(data["data"]).hex()
        params = "\n  ".join(f"{k}: {v}" for k, v in data.items())
        return f"{self.__class__.__name__}:\n  {params}"


class ConfirmationsProgressBar:
    """
    A progress bar tracking the confirmations of a transaction.
    """

    def __init__(self, confirmations: int):
        self._req_confs = confirmations
        self._bar = tqdm(range(confirmations))
        self._confs = 0

    def __enter__(self):
        self._update_bar(0)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self._bar.close()

    @property
    def confs(self) -> int:
        """
        The number of confirmations that have occurred.

        Returns:
            int: The total number of confirmations that have occurred.
        """
        return self._confs

    @confs.setter
    def confs(self, new_value):
        if new_value == self._confs:
            return

        diff = new_value - self._confs
        self._confs = new_value
        self._update_bar(diff)

    def _update_bar(self, amount: int):
        self._set_description()
        self._bar.update(amount)
        self._bar.refresh()

    def _set_description(self):
        self._bar.set_description(f"Confirmations ({self._confs}/{self._req_confs})")


class ReceiptAPI(BaseInterfaceModel):
    """
    An abstract class to represent a transaction receipt. The receipt
    contains information about the transaction, such as the status
    and required confirmations.

    **NOTE**: Use a ``required_confirmations`` of ``0`` in your transaction
    to not wait for confirmations.

    Get a receipt by making transactions in ``ape``, such as interacting with
    a :class:`ape.contracts.base.ContractInstance`.
    """

    contract_address: Optional[str] = None
    block_number: int
    data: bytes = b""
    gas_limit: int
    gas_price: int
    gas_used: int
    logs: List[dict] = []
    nonce: Optional[int] = None
    receiver: str
    required_confirmations: int = 0
    sender: str
    status: int
    txn_hash: str
    value: int = 0

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.txn_hash}>"

    @property
    def failed(self) -> bool:
        """
        Whether the receipt represents a failing transaction.
        Ecosystem plugins override this property when their receipts
        are able to be failing.
        """

        return False

    @property
    @abstractmethod
    def total_fees_paid(self) -> int:
        """
        The total amount of fees paid for the transaction.
        """

    @property
    @abstractmethod
    def ran_out_of_gas(self) -> bool:
        """
        Check if a transaction has ran out of gas and failed.

        Returns:
            bool:  ``True`` when the transaction failed and used the
            same amount of gas as the given ``gas_limit``.
        """

    @property
    def trace(self) -> Iterator[TraceFrame]:
        """
        The trace of the transaction, if available from your provider.
        """
        return self.provider.get_transaction_trace(txn_hash=self.txn_hash)

    @property
    def _explorer(self) -> Optional[ExplorerAPI]:
        return self.provider.network.explorer

    @property
    def _block_time(self) -> int:
        return self.provider.network.block_time

    @property
    def _confirmations_occurred(self) -> int:
        latest_block = self.provider.get_block("latest")

        if latest_block.number is None:
            return 0

        return latest_block.number - self.block_number

    @abstractmethod
    def decode_logs(
        self,
        abi: Optional[
            Union[List[Union[EventABI, "ContractEvent"]], Union[EventABI, "ContractEvent"]]
        ] = None,
    ) -> Iterator[ContractLog]:
        """
        Decode the logs on the receipt.

        Args:
            abi (``EventABI``): The ABI of the event to decode into logs.

        Returns:
            Iterator[:class:`~ape.types.ContractLog`]
        """

    def raise_for_status(self):
        """
        Handle provider-specific errors regarding a non-successful
        :class:`~api.providers.TransactionStatusEnum`.
        """

    def await_confirmations(self) -> "ReceiptAPI":
        """
        Wait for a transaction to be considered confirmed.

        Returns:
            :class:`~ape.api.ReceiptAPI`: The receipt that is now confirmed.
        """

        try:
            self.raise_for_status()
        except TransactionError:
            # Skip waiting for confirmations when the transaction has failed.
            return self

        # Wait for nonce from provider to increment.
        sender_nonce = self.provider.get_nonce(self.sender)
        iterations_timeout = 20
        iteration = 0

        while sender_nonce == self.nonce:  # type: ignore
            time.sleep(1)
            sender_nonce = self.provider.get_nonce(self.sender)
            iteration += 1
            if iteration == iterations_timeout:
                raise TransactionError(message="Timeout waiting for sender's nonce to increase.")

        if self.required_confirmations == 0:
            # The transaction might not yet be confirmed but
            # the user is aware of this. Or, this is a development environment.
            return self

        confirmations_occurred = self._confirmations_occurred
        if confirmations_occurred >= self.required_confirmations:
            return self

        # If we get here, that means the transaction has been recently submitted.
        log_message = f"Submitted {self.txn_hash}"
        if self._explorer:
            explorer_url = self._explorer.get_transaction_url(self.txn_hash)
            if explorer_url:
                log_message = f"{log_message}\n{self._explorer.name} URL: {explorer_url}"

        logger.info(log_message)

        with ConfirmationsProgressBar(self.required_confirmations) as progress_bar:
            while confirmations_occurred < self.required_confirmations:
                confirmations_occurred = self._confirmations_occurred
                progress_bar.confs = confirmations_occurred

                if confirmations_occurred == self.required_confirmations:
                    break

                time_to_sleep = int(self._block_time / 2)
                time.sleep(time_to_sleep)

        return self

    @raises_not_implemented
    def show_trace(self, verbose: bool = False, file: IO[str] = sys.stdout):
        """
        Display the complete sequence of contracts and methods called during
        the transaction.

        Args:
            verbose (bool): Set to ``True`` to include more information.
            file (IO[str]): The file to send output to. Defaults to stdout.
        """
