import sys
import time
from abc import abstractmethod
from collections.abc import Iterator
from datetime import datetime
from functools import cached_property
from typing import IO, TYPE_CHECKING, Any, NoReturn, Optional, Union

from eth_pydantic_types import HexBytes, HexStr
from eth_utils import is_hex, to_hex, to_int
from ethpm_types.abi import EventABI, MethodABI
from pydantic import ConfigDict, field_validator
from pydantic.fields import Field
from tqdm import tqdm  # type: ignore

from ape.api.explorers import ExplorerAPI
from ape.exceptions import (
    NetworkError,
    ProviderNotConnectedError,
    SignatureError,
    TransactionError,
    TransactionNotFoundError,
)
from ape.logging import logger
from ape.types.address import AddressType
from ape.types.basic import HexInt
from ape.types.events import ContractLogContainer
from ape.types.gas import AutoGasLimit
from ape.types.signatures import TransactionSignature
from ape.types.trace import SourceTraceback
from ape.utils.basemodel import BaseInterfaceModel, ExtraAttributesMixin, ExtraModelAttributes
from ape.utils.misc import log_instead_of_fail, raises_not_implemented

if TYPE_CHECKING:
    from ape.api.providers import BlockAPI
    from ape.api.trace import TraceAPI
    from ape.contracts import ContractEvent


class TransactionAPI(BaseInterfaceModel):
    """
    An API class representing a transaction.
    Ecosystem plugins implement one or more of transaction APIs
    depending on which schemas they permit,
    such as typed-transactions from `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__.
    """

    chain_id: Optional[HexInt] = Field(default=0, alias="chainId")
    receiver: Optional[AddressType] = Field(default=None, alias="to")
    sender: Optional[AddressType] = Field(default=None, alias="from")
    gas_limit: Optional[HexInt] = Field(default=None, alias="gas")
    nonce: Optional[HexInt] = None  # NOTE: `Optional` only to denote using default behavior
    value: HexInt = 0
    data: HexBytes = HexBytes("")
    type: HexInt
    max_fee: Optional[HexInt] = None
    max_priority_fee: Optional[HexInt] = None

    # If left as None, will get set to the network's default required confirmations.
    required_confirmations: Optional[HexInt] = Field(default=None, exclude=True)

    signature: Optional[TransactionSignature] = Field(default=None, exclude=True)

    model_config = ConfigDict(populate_by_name=True)

    def __init__(self, *args, **kwargs):
        raise_on_revert = kwargs.pop("raise_on_revert", True)
        super().__init__(*args, **kwargs)
        self._raise_on_revert = raise_on_revert

    @field_validator("gas_limit", mode="before")
    @classmethod
    def validate_gas_limit(cls, value):
        if value is None:
            if not cls.network_manager.active_provider:
                raise NetworkError("Must be connected to use default gas config.")

            value = cls.network_manager.active_provider.network.gas_limit

        if value == "auto" or isinstance(value, AutoGasLimit):
            return None  # Delegate to `ProviderAPI.estimate_gas_cost`

        elif value == "max":
            if not cls.network_manager.active_provider:
                raise NetworkError("Must be connected to use 'max'.")

            return cls.network_manager.active_provider.max_gas

        elif isinstance(value, str) and is_hex(value):
            return to_int(hexstr=value)

        elif isinstance(value, str) and value.isnumeric():
            return to_int(value)

        return value

    @property
    def raise_on_revert(self) -> bool:
        return self._raise_on_revert

    @raise_on_revert.setter
    def raise_on_revert(self, value):
        self._raise_on_revert = value

    @property
    def total_transfer_value(self) -> int:
        """
        The total amount of WEI that a transaction could use.
        Useful for determining if an account balance can afford
        to submit the transaction.
        """
        if self.max_fee is None:
            raise TransactionError("`self.max_fee` must not be None.")

        return self.value + self.max_fee

    @property
    @abstractmethod
    def txn_hash(self) -> HexBytes:
        """
        The calculated hash of the transaction.
        """

    @property
    def receipt(self) -> Optional["ReceiptAPI"]:
        """
        This transaction's associated published receipt, if it exists.
        """
        try:
            txn_hash = to_hex(self.txn_hash)
        except SignatureError:
            return None

        try:
            return self.chain_manager.get_receipt(txn_hash)
        except (TransactionNotFoundError, ProviderNotConnectedError):
            return None

    @property
    def trace(self) -> "TraceAPI":
        """
        The transaction trace. Only works if this transaction was published
        and you are using a provider that support tracing.

        Raises:
            :class:`~ape.exceptions.APINotImplementedError`: When using a provider
              that does not support tracing.
        """
        return self.provider.get_transaction_trace(to_hex(self.txn_hash))

    @abstractmethod
    def serialize_transaction(self) -> bytes:
        """
        Serialize the transaction
        """

    @log_instead_of_fail(default="<TransactionAPI>")
    def __repr__(self) -> str:
        # NOTE: Using JSON mode for style.
        data = self.model_dump(mode="json")
        params = ", ".join(f"{k}={v}" for k, v in data.items())
        cls_name = getattr(type(self), "__name__", TransactionAPI.__name__)
        return f"<{cls_name} {params}>"

    def __str__(self) -> str:
        # NOTE: Using JSON mode for style.
        data = self.model_dump(mode="json")
        if len(data["data"]) > 9:
            # only want to specify encoding if data["data"] is a string
            if isinstance(data["data"], str):
                data["data"] = (
                    "0x"
                    + bytes(data["data"][:3], encoding="utf8").hex()
                    + "..."
                    + bytes(data["data"][-3:], encoding="utf8").hex()
                )
            else:
                data["data"] = (
                    to_hex(bytes(data["data"][:3])) + "..." + to_hex(bytes(data["data"][-3:]))
                )
        else:
            if isinstance(data["data"], str):
                data["data"] = to_hex(bytes(data["data"], encoding="utf8"))
            else:
                data["data"] = to_hex(bytes(data["data"]))
        params = "\n  ".join(f"{k}: {v}" for k, v in data.items())
        cls_name = getattr(type(self), "__name__", TransactionAPI.__name__)
        return f"{cls_name}:\n  {params}"


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


class ReceiptAPI(ExtraAttributesMixin, BaseInterfaceModel):
    """
    An abstract class to represent a transaction receipt. The receipt
    contains information about the transaction, such as the status
    and required confirmations.

    **NOTE**: Use a ``required_confirmations`` of ``0`` in your transaction
    to not wait for confirmations.

    Get a receipt by making transactions in ``ape``, such as interacting with
    a :class:`ape.contracts.base.ContractInstance`.
    """

    contract_address: Optional[AddressType] = None
    block_number: HexInt
    gas_used: HexInt
    logs: list[dict] = []
    status: HexInt
    txn_hash: HexStr
    transaction: TransactionAPI
    _error: Optional[TransactionError] = None

    @log_instead_of_fail(default="<ReceiptAPI>")
    def __repr__(self) -> str:
        cls_name = getattr(self.__class__, "__name__", ReceiptAPI.__name__)
        return f"<{cls_name} {self.txn_hash}>"

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        yield ExtraModelAttributes(name="transaction", attributes=lambda: vars(self.transaction))

    @field_validator("transaction", mode="before")
    @classmethod
    def _validate_transaction(cls, value):
        if not isinstance(value, dict):
            # Already a `TransactionAPI`.
            return value

        # Attempt to create a transaction model for the data.
        if provider := cls.network_manager.active_provider:
            ecosystem = provider.network.ecosystem
        else:
            logger.warning(
                "Given raw-transaction data when not connected to any provider. "
                "Network is unknown. Assuming EVM-like transaction model."
            )
            ecosystem = cls.network_manager.ethereum

        return ecosystem.create_transaction(**value)

    @cached_property
    def debug_logs_typed(self) -> list[tuple[Any]]:
        """Return any debug log data outputted by the transaction."""
        return []

    @cached_property
    def debug_logs_lines(self) -> list[str]:
        """
        Return any debug log data outputted by the transaction as strings suitable for printing
        """
        return [" ".join(map(str, ln)) for ln in self.debug_logs_typed]

    @property
    def error(self) -> Optional[TransactionError]:
        return self._error

    @error.setter
    def error(self, value: TransactionError):
        self._error = value

    def show_debug_logs(self):
        """
        Output debug logs to logging system
        """
        for ln in self.debug_logs_lines:
            logger.info(f"[DEBUG-LOG] {ln}")

    @property
    def failed(self) -> bool:
        """
        Whether the receipt represents a failing transaction.
        Ecosystem plugins override this property when their receipts
        are able to be failing.
        """
        return False

    @property
    def confirmed(self) -> bool:
        """
        ``True`` when the number of confirmations is equal or greater
        to the required amount of confirmations.
        """
        return self._confirmations_occurred == self.required_confirmations

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
        Check if a transaction ran out of gas and failed.

        Returns:
            bool:  ``True`` when the transaction failed and used the
            same amount of gas as the given ``gas_limit``.
        """

    @property
    def trace(self) -> "TraceAPI":
        """
        The :class:`~ape.api.trace.TraceAPI` of the transaction.
        """
        return self.provider.get_transaction_trace(self.txn_hash)

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

    @cached_property
    def block(self) -> "BlockAPI":
        return self.chain_manager.blocks[self.block_number]

    @property
    def timestamp(self) -> int:
        return self.block.timestamp

    @property
    def datetime(self) -> datetime:
        return self.block.datetime

    @cached_property
    def events(self) -> ContractLogContainer:
        """
        All the events that were emitted from this call.
        """

        return self.decode_logs()  # Decodes all logs by default.

    @abstractmethod
    def decode_logs(
        self,
        abi: Optional[
            Union[list[Union[EventABI, "ContractEvent"]], Union[EventABI, "ContractEvent"]]
        ] = None,
    ) -> ContractLogContainer:
        """
        Decode the logs on the receipt.

        Args:
            abi (``EventABI``): The ABI of the event to decode into logs.

        Returns:
            list[:class:`~ape.types.ContractLog`]
        """

    def raise_for_status(self) -> Optional[NoReturn]:
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
        # NOTE: Even when required_confirmations is `0`, we want to wait for the nonce to
        #   increment. Otherwise, users may end up with invalid nonce errors in tests.
        self._await_sender_nonce_increment()
        if self.required_confirmations == 0 or self._check_error_status() or self.confirmed:
            return self

        # Confirming now.
        self._log_submission()
        self._await_confirmations()
        return self

    def _await_sender_nonce_increment(self):
        if not self.sender:
            return

        iterations_timeout = 20
        iteration = 0
        sender_nonce = self.provider.get_nonce(self.sender)
        while sender_nonce == self.nonce:
            time.sleep(1)
            sender_nonce = self.provider.get_nonce(self.sender)
            iteration += 1
            if iteration != iterations_timeout:
                continue

            tx_err = TransactionError("Timeout waiting for sender's nonce to increase.")
            self.error = tx_err
            if self.transaction.raise_on_revert:
                raise tx_err
            else:
                break

    def _log_submission(self):
        if explorer_url := self._explorer and self._explorer.get_transaction_url(self.txn_hash):
            log_message = f"Submitted {explorer_url}"
        else:
            log_message = f"Submitted {self.txn_hash}"

        logger.info(log_message)

    def _check_error_status(self) -> bool:
        try:
            self.raise_for_status()
        except TransactionError:
            # Skip waiting for confirmations when the transaction has failed.
            return True

        return False

    def _await_confirmations(self):
        if self.required_confirmations <= 0:
            return

        with ConfirmationsProgressBar(self.required_confirmations) as progress_bar:
            while not self.confirmed:
                confirmations_occurred = self._confirmations_occurred
                if confirmations_occurred >= self.required_confirmations:
                    break

                progress_bar.confs = confirmations_occurred
                time_to_sleep = int(self._block_time / 2)
                time.sleep(time_to_sleep)

    @property
    def method_called(self) -> Optional[MethodABI]:
        """
        The method ABI of the method called to produce this receipt.
        """
        return None

    @property
    def return_value(self) -> Any:
        """
        Obtain the final return value of the call. Requires tracing to function,
        since this is not available from the receipt object.
        """
        if trace := self.trace:
            ret_val = trace.return_value
            return ret_val[0] if isinstance(ret_val, tuple) and len(ret_val) == 1 else ret_val

        return None

    @property
    @raises_not_implemented
    def source_traceback(self) -> SourceTraceback:  # type: ignore[empty-body]
        """
        A Pythonic style traceback for both failing and non-failing receipts.
        Requires a provider that implements
        :meth:~ape.api.providers.ProviderAPI.get_transaction_trace`.
        """

    @raises_not_implemented
    def show_trace(self, verbose: bool = False, file: IO[str] = sys.stdout):
        """
        Display the complete sequence of contracts and methods called during
        the transaction.

        Args:
            verbose (bool): Set to ``True`` to include more information.
            file (IO[str]): The file to send output to. Defaults to stdout.
        """

    @raises_not_implemented
    def show_gas_report(self, file: IO[str] = sys.stdout):
        """
        Display a gas report for the calls made in this transaction.
        """

    @raises_not_implemented
    def show_source_traceback(self):
        """
        Show a receipt traceback mapping to lines in the source code.
        Only works when the contract type and source code are both available,
        like in local projects.
        """

    @raises_not_implemented
    def show_events(self):
        """
        Show the events from the receipt.
        """

    def track_gas(self):
        """
        Track this receipt's gas in the on-going session gas-report.
        Requires using a provider that supports transaction traces
        to get full data. Else, is limited to receipt-level data.
        This gets called when running tests with the ``--gas`` flag.
        """
        address = self.receiver or self.contract_address
        if not address or not self._test_runner:
            return

        if self.provider.supports_tracing and (trace := self.trace):
            tracker = self._test_runner.gas_tracker
            tracker.append_gas(trace, address)

        elif (
            (contract_type := self.chain_manager.contracts.get(address))
            and contract_type.source_id
            and (method := self.method_called)
        ):
            # Can only track top-level gas.
            if contract := self.local_project._create_contract_source(contract_type):
                self._test_runner.gas_tracker.append_toplevel_gas(contract, method, self.gas_used)

    def track_coverage(self):
        """
        Track this receipt's source code coverage in the on-going
        session coverage report. Requires using a provider that supports
        transaction traces to track full coverage. Else, is limited
        to receipt-level tracking. This gets called when running tests with
        the ``--coverage`` flag.
        """

        if not self.network_manager.active_provider or not self._test_runner:
            return

        if not (address := self.receiver):
            # NOTE: Deploy txns are currently not tracked!
            return

        tracker = self._test_runner.coverage_tracker
        if self.provider.supports_tracing and (traceback := self.source_traceback):
            if len(traceback) > 0:
                tracker.cover(traceback)

        elif method := self.method_called:
            # Unable to track detailed coverage like statement or branch
            # The user will receive a warning at the end regarding this.
            # At the very least, we can track function coverage.
            contract_type = self.chain_manager.contracts.get(address)
            if not contract_type or not contract_type.source_id:
                return

            if contract := self.local_project._create_contract_source(contract_type):
                tracker.hit_function(contract, method)
