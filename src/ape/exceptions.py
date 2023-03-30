import sys
import time
import traceback
from inspect import getframeinfo, stack
from pathlib import Path
from typing import TYPE_CHECKING, List, Optional

import click
from eth_utils import humanize_hash
from rich import print as rich_print

from ape.logging import LogLevel, logger

if TYPE_CHECKING:
    from ape.api.networks import NetworkAPI
    from ape.api.providers import SubprocessProvider
    from ape.api.transactions import TransactionAPI
    from ape.types import BlockID, SnapshotID


class ApeException(Exception):
    """
    An exception raised by ape.
    """


class APINotImplementedError(ApeException, NotImplementedError):
    """
    An error raised when an API class does not implement an abstract method.
    """


class AccountsError(ApeException):
    """
    Raised when a problem occurs when using accounts.
    """


class AliasAlreadyInUseError(AccountsError):
    """
    Raised when attempting to add an account using an alias
    that already maps to another account.
    """

    def __init__(self, alias: str):
        self.alias = alias
        super().__init__(f"Account with alias '{alias}' already in use.")


class SignatureError(AccountsError):
    """
    Raised when there are issues with signing.
    """


class ContractError(ApeException):
    """
    Raised when issues occur with contracts.
    """


class ArgumentsLengthError(ContractError):
    """
    Raised when calling a contract method with the wrong number of arguments.
    """

    def __init__(self, arguments_length: int, inputs_length: Optional[int] = None):
        abi_suffix = f" ({inputs_length})" if inputs_length else ""
        message = (
            f"The number of the given arguments ({arguments_length}) "
            f"do not match what is defined in the "
            f"ABI{abi_suffix}."
        )
        super().__init__(message)


class DecodingError(ContractError):
    """
    Raised when issues occur while decoding data from
    a contract call, transaction, or event.
    """

    def __init__(self, message: Optional[str] = None):
        message = message or "Output corrupted."
        super().__init__(message)


class TransactionError(ContractError):
    """
    Raised when issues occur related to transactions.
    """

    DEFAULT_MESSAGE = "Transaction failed."

    def __init__(
        self,
        message: Optional[str] = None,
        base_err: Optional[Exception] = None,
        code: Optional[int] = None,
        txn: Optional["TransactionAPI"] = None,
    ):
        if not message:
            message = str(base_err) if base_err else self.DEFAULT_MESSAGE
        self.message = message

        self.base_err = base_err
        self.code = code
        self.txn = txn

        ex_message = f"({code}) {message}" if code else message
        super().__init__(ex_message)


class VirtualMachineError(TransactionError):
    """
    Raised when a transaction error occurs in a virtual machine.
    """


class ContractLogicError(VirtualMachineError):
    """
    Raised when there is a contract-defined revert,
    such as from an assert/require statement.
    """

    def __init__(
        self, revert_message: Optional[str] = None, txn: Optional["TransactionAPI"] = None
    ):
        super().__init__(message=revert_message, txn=txn)

    @property
    def revert_message(self):
        return self.message

    @classmethod
    def from_error(cls, err: Exception):
        """
        Creates this class from the error message of the given
        error.

        This should be overridden whenever possible to handle
        provider-specific use-cases for raising this error.
        """
        return cls(str(err))


class OutOfGasError(VirtualMachineError):
    """
    Raised when detecting a transaction failed because it ran
    out of gas.
    """

    def __init__(self, code: Optional[int] = None, txn: Optional["TransactionAPI"] = None):
        super().__init__("The transaction ran out of gas.", code=code, txn=txn)


class NetworkError(ApeException):
    """
    Raised when a problem occurs when using blockchain networks.
    """


class NetworkNotFoundError(NetworkError):
    """
    Raised when the network with the given name was not found.
    """

    def __init__(self, network: str):
        self.network = network
        message = f"No network named '{network}'."
        super().__init__(message)


class CompilerError(ApeException):
    """
    Raised when unable to compile.
    """


class ProjectError(ApeException):
    """
    Raised when problems occur in a project.
    """


class ConversionError(ApeException):
    """
    Raised when unable to convert a value.
    """


class ProviderError(ApeException):
    """
    Raised when a problem occurs when using providers.
    """


class BlockNotFoundError(ProviderError):
    """
    Raised when unable to find a block.
    """

    def __init__(self, block_id: "BlockID"):
        if isinstance(block_id, bytes):
            block_id_str = block_id.hex()
        else:
            block_id_str = str(block_id)

        super().__init__(f"Block with ID '{block_id_str}' not found.")


class TransactionNotFoundError(ProviderError):
    """
    Raised when unable to find a transaction.
    """

    def __init__(self, txn_hash: str):
        super().__init__(f"Transaction '{txn_hash}' not found.")


class NetworkMismatchError(ProviderError):
    """
    Raised when connecting a provider to the wrong network.
    """

    def __init__(self, chain_id: int, network: "NetworkAPI"):
        message = (
            f"Provider connected to chain ID '{chain_id}', which does not match "
            f"network chain ID '{network.chain_id}'. Are you connected to '{network.name}'?"
        )
        super().__init__(message)


class ProviderNotConnectedError(ProviderError):
    """
    Raised when not connected to a provider.
    """

    def __init__(self):
        super().__init__("Not connected to a network provider.")


class ConfigError(ApeException):
    """
    Raised when a problem occurs from the configuration file.
    """


class ChainError(ApeException):
    """
    Raised when problems occur in the :class:`~ape.managers.chain.ChainManager`.
    """


class UnknownSnapshotError(ChainError):
    """
    Raised when given an unknown snapshot ID.
    """

    def __init__(self, snapshot_id: "SnapshotID"):
        if isinstance(snapshot_id, bytes):
            # Is block hash
            snapshot_id = humanize_hash(snapshot_id)  # type: ignore

        super().__init__(f"Unknown snapshot ID '{str(snapshot_id)}'.")


class QueryEngineError(ApeException):
    """
    Raised when issues occur in a query engine.
    """


class SubprocessError(ApeException):
    """
    An error raised whilst managing a subprocess.
    """


class SubprocessTimeoutError(SubprocessError):
    """
    A context-manager exception that raises if its operations exceed
    the given timeout seconds.

    This implementation was inspired from py-geth.
    """

    def __init__(
        self,
        provider: "SubprocessProvider",
        message: Optional[str] = None,
        seconds: Optional[int] = None,
        exception: Optional[Exception] = None,
        *args,
        **kwargs,
    ):
        self._provider = provider
        self._message = message or "Timed out waiting for process."
        self._seconds = seconds
        self._exception = exception
        self._start_time: Optional[float] = None
        self._is_running: Optional[bool] = None

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return False

    def __str__(self):
        if self._seconds in [None, ""]:
            return ""

        return self._message

    @property
    def expire_at(self) -> float:
        if self._seconds is None:
            raise ValueError("Timeouts with 'seconds == None' do not have an expiration time.")
        elif self._start_time is None:
            raise ValueError("Timeout has not been started.")

        return self._start_time + self._seconds

    def start(self):
        if self._is_running is not None:
            raise ValueError("Timeout has already been started.")

        self._start_time = time.time()
        self._is_running = True

    def check(self):
        if self._is_running is None:
            raise ValueError("Timeout has not been started.")

        elif self._is_running is False:
            raise ValueError("Timeout has already been cancelled.")

        elif self._seconds is None:
            return

        elif time.time() > self.expire_at:
            self.cancel()
            self._is_running = False

            if isinstance(self._exception, type):
                raise self._exception(str(self))

            elif isinstance(self._exception, Exception):
                raise self._exception

            raise self

    def cancel(self):
        if self._provider:
            self._provider.stop()

        self._is_running = False


class RPCTimeoutError(SubprocessTimeoutError):
    def __init__(
        self,
        provider: "SubprocessProvider",
        seconds: Optional[int] = None,
        exception: Optional[Exception] = None,
        *args,
        **kwargs,
    ):
        error_message = (
            "Timed out waiting for successful RPC connection to "
            f"the '{provider.process_name}' process ({seconds} seconds)."
        )
        kwargs["message"] = error_message
        if seconds:
            kwargs["seconds"] = seconds
        if exception:
            kwargs["exception"] = exception

        super().__init__(provider, *args, **kwargs)


def handle_ape_exception(err: ApeException, base_paths: List[Path]) -> bool:
    """
    Handle a transaction error by showing relevant stack frames,
    including custom contract frames added to the exception.
    This method must be called within an ``except`` block or with
    an exception on the exc-stack.

    Args:
        err (:class:`~ape.exceptions.ApeException`): The transaction error
          being handled.
        base_paths (List[Path]): Source base paths for allowed frames.

    Returns:
        bool: ``True`` if outputted something.
    """

    tb = traceback.extract_tb(sys.exc_info()[2])
    relevant_tb = [f for f in tb if any(str(p) in f.filename for p in base_paths)]
    if not relevant_tb:
        return False

    click.echo()
    formatted_tb = traceback.format_list(relevant_tb)
    rich_print("".join(formatted_tb))

    # Prevent double logging traceback.
    logger.error(Abort.from_ape_exception(err, show_traceback=False))
    return True


class Abort(click.ClickException):
    """
    A wrapper around a CLI exception. When you raise this error,
    the error is nicely printed to the terminal. This is
    useful for all user-facing errors.
    """

    def __init__(self, message: Optional[str] = None):
        if not message:
            caller = getframeinfo(stack()[1][0])
            file_path = Path(caller.filename)
            location = file_path.name if file_path.is_file() else caller.filename
            message = f"Operation aborted in {location}::{caller.function} on line {caller.lineno}."

        super().__init__(message)

    @classmethod
    def from_ape_exception(cls, exc: ApeException, show_traceback: Optional[bool] = None):
        show_traceback = (
            logger.level == LogLevel.DEBUG.value if show_traceback is None else show_traceback
        )
        if show_traceback:
            tb = traceback.format_exc()
            err_message = tb or str(exc)
        else:
            err_message = str(exc)

        return Abort(f"({type(exc).__name__}) {err_message}")

    def show(self, file=None):
        """
        Override default ``show`` to print CLI errors in red text.
        """

        logger.error(self.format_message())
