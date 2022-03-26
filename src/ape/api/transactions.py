import time
from enum import Enum, IntEnum
from typing import TYPE_CHECKING, Iterator, List, Optional, Union

from ethpm_types.abi import EventABI
from pydantic.fields import Field
from tqdm import tqdm  # type: ignore

from ape.api.explorers import ExplorerAPI
from ape.exceptions import TransactionError
from ape.logging import logger
from ape.types import ContractLog, TransactionSignature
from ape.utils import BaseInterfaceModel, abstractmethod

if TYPE_CHECKING:
    from ape.contracts import ContractEvent


class TransactionType(Enum):
    """
    Transaction enumerable type constants defined by
    `EIP-2718 <https://eips.ethereum.org/EIPS/eip-2718>`__.
    """

    STATIC = "0x00"
    DYNAMIC = "0x02"  # EIP-1559


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
    type: TransactionType = TransactionType.STATIC
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


class TransactionStatusEnum(IntEnum):
    """
    An ``Enum`` class representing the status of a transaction.
    """

    FAILING = 0
    """The transaction has failed or is in the process of failing."""

    NO_ERROR = 1
    """
    The transaction is successful and is confirmed or is in the process
    of getting confirmed.
    """


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

    txn_hash: str
    status: TransactionStatusEnum
    block_number: int
    gas_used: int
    gas_price: int
    gas_limit: int
    logs: List[dict] = []
    contract_address: Optional[str] = None
    required_confirmations: int = 0
    sender: str
    receiver: str
    nonce: Optional[int] = None

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self.txn_hash}>"

    def raise_for_status(self):
        """
        Handle provider-specific errors regarding a non-successful
        :class:`~api.providers.TransactionStatusEnum`.
        """

    @property
    def ran_out_of_gas(self) -> bool:
        """
        Check if a transaction has ran out of gas and failed.

        Returns:
            bool:  ``True`` when the transaction failed and used the
            same amount of gas as the given ``gas_limit``.
        """
        return self.status == TransactionStatusEnum.FAILING and self.gas_used == self.gas_limit

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

    def decode_logs(self, abi: Union[EventABI, "ContractEvent"]) -> Iterator[ContractLog]:
        """
        Decode the logs on the receipt.

        Args:
            abi (``EventABI``): The ABI of the event to decode into logs.

        Returns:
            Iterator[:class:`~ape.types.ContractLog`]
        """
        if not isinstance(abi, EventABI):
            abi = abi.abi

        yield from self.provider.network.ecosystem.decode_logs(abi, self.logs)

    def await_confirmations(self) -> "ReceiptAPI":
        """
        Wait for a transaction to be considered confirmed.

        Returns:
            :class:`~ape.api.ReceiptAPI`: The receipt that is now confirmed.
        """
        # Wait for nonce from provider to increment.
        sender_nonce = self.provider.get_nonce(self.sender)
        while sender_nonce == self.nonce:  # type: ignore
            time.sleep(1)
            sender_nonce = self.provider.get_nonce(self.sender)

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
