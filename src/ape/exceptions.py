import difflib
import sys
import tempfile
import time
import traceback
from inspect import getframeinfo, stack
from pathlib import Path
from types import CodeType, TracebackType
from typing import TYPE_CHECKING, Any, Collection, Dict, Iterator, List, Optional, Union, cast

import click
from eth_typing import Hash32
from eth_utils import humanize_hash
from ethpm_types.abi import ConstructorABI, ErrorABI, MethodABI
from rich import print as rich_print

from ape.logging import LogLevel, logger

if TYPE_CHECKING:
    from ape.api.networks import NetworkAPI
    from ape.api.providers import SubprocessProvider
    from ape.api.transactions import ReceiptAPI, TransactionAPI
    from ape.types import AddressType, BlockID, SnapshotID, SourceTraceback, TraceFrame


FailedTxn = Union["TransactionAPI", "ReceiptAPI"]


class ApeException(Exception):
    """
    An exception raised by ape.
    """


class ApeIndexError(ApeException, IndexError):
    """
    An exception that is also an IndexError.
    Useful for nicely displaying IndexErrors.
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


class ContractDataError(ApeException):
    """
    Raised when issues occur with local contract.
    **NOTE**: This error has nothing to do with on-chain
    contract logic errors; it is more about ABI-related
    issues and alike.
    """


class ArgumentsLengthError(ContractDataError):
    """
    Raised when calling a contract method with the wrong number of arguments.
    """

    def __init__(
        self,
        arguments_length: int,
        inputs: Union[MethodABI, ConstructorABI, int, List, None] = None,
        **kwargs,
    ):
        prefix = (
            f"The number of the given arguments ({arguments_length}) "
            f"do not match what is defined in the ABI"
        )
        if inputs is None:
            super().__init__(f"{prefix}.")
            return

        inputs_ls: List[Union[MethodABI, ConstructorABI, int]] = (
            inputs if isinstance(inputs, list) else [inputs]
        )
        if not inputs_ls:
            suffix = ""
        elif any(not isinstance(x, int) for x in inputs_ls):
            # Handle ABI arguments
            parts = ""
            for idx, ipt in enumerate(inputs_ls):
                if isinstance(ipt, int):
                    part = f"{ipt}"
                else:
                    # Signature without outputs.
                    input_args = ", ".join(i.signature for i in ipt.inputs)
                    part = f"{getattr(ipt, 'name', '__init__')}({input_args})"

                parts = f"{parts}\n\t{part}"

            suffix = f":\n{parts}"

        else:
            # Was only given integers.
            options = ", ".join([str(x) for x in inputs_ls])
            one_of = "one of " if len(inputs_ls) > 1 else ""
            suffix = f" ({one_of}{options})"

        super().__init__(f"{prefix}{suffix}")


class DecodingError(ContractDataError):
    """
    Raised when issues occur while decoding data from
    a contract call, transaction, or event.
    """

    def __init__(self, message: Optional[str] = None):
        message = message or "Output corrupted."
        super().__init__(message)


class MethodNonPayableError(ContractDataError):
    """
    Raises when sending funds to a non-payable method
    """


class TransactionError(ApeException):
    """
    Raised when issues occur related to transactions.
    """

    DEFAULT_MESSAGE = "Transaction failed."

    def __init__(
        self,
        message: Optional[str] = None,
        base_err: Optional[Exception] = None,
        code: Optional[int] = None,
        txn: Optional[FailedTxn] = None,
        trace: Optional[Iterator["TraceFrame"]] = None,
        contract_address: Optional["AddressType"] = None,
        source_traceback: Optional["SourceTraceback"] = None,
    ):
        message = message or (str(base_err) if base_err else self.DEFAULT_MESSAGE)
        self.message = message
        self.base_err = base_err
        self.code = code
        self.txn = txn
        self.trace = trace
        self.contract_address = contract_address
        self.source_traceback: Optional["SourceTraceback"] = source_traceback
        ex_message = f"({code}) {message}" if code else message

        # Finalizes expected revert message.
        super().__init__(ex_message)
        self._set_tb()

    @property
    def address(self) -> Optional["AddressType"]:
        return (
            self.contract_address
            or getattr(self.txn, "receiver", None)
            or getattr(self.txn, "contract_address", None)
        )

    def _set_tb(self):
        if not self.source_traceback and self.txn:
            self.source_traceback = _get_ape_traceback(self.txn)

        if (src_tb := self.source_traceback) and self.txn is not None:
            # Create a custom Pythonic traceback using lines from the sources
            # found from analyzing the trace of the transaction.
            if py_tb := _get_custom_python_traceback(self, self.txn, src_tb):
                self.__traceback__ = py_tb


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
        self,
        revert_message: Optional[str] = None,
        txn: Optional[FailedTxn] = None,
        trace: Optional[Iterator["TraceFrame"]] = None,
        contract_address: Optional["AddressType"] = None,
        source_traceback: Optional["SourceTraceback"] = None,
        base_err: Optional[Exception] = None,
    ):
        self.txn = txn
        self.trace = trace
        self.contract_address = contract_address

        super().__init__(
            base_err=base_err,
            contract_address=contract_address,
            message=revert_message,
            source_traceback=source_traceback,
            trace=trace,
            txn=txn,
        )

        if revert_message is None and source_traceback is not None and (dev := self.dev_message):
            try:
                # Attempt to use dev message as main exception message.
                self.message = dev
            except Exception:
                pass

    @property
    def revert_message(self):
        return self.message

    @property
    def dev_message(self) -> Optional[str]:
        """
        The dev-string message of the exception.

        Raises:
            ``ValueError``: When unable to get dev message.
        """

        return self.source_traceback.revert_type if self.source_traceback else None

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

    def __init__(
        self,
        code: Optional[int] = None,
        txn: Optional[FailedTxn] = None,
        base_err: Optional[Exception] = None,
    ):
        super().__init__("The transaction ran out of gas.", code=code, txn=txn, base_err=base_err)


class NetworkError(ApeException):
    """
    Raised when a problem occurs when using blockchain networks.
    """


class EcosystemNotFoundError(NetworkError):
    """
    Raised when the ecosystem with the given name was not found.
    """

    def __init__(self, ecosystem: str, options: Optional[Collection[str]] = None):
        self.ecosystem = ecosystem
        self.options = options
        message = f"No ecosystem named '{ecosystem}'."
        if options:
            close_matches = difflib.get_close_matches(ecosystem, options, cutoff=0.6)
            if close_matches:
                message = f"{message} Did you mean '{', '.join(close_matches)}'?"
            else:
                # No close matches. Show all the options.
                options_str = "\n".join(sorted(options))
                message = f"{message} Options:\n{options_str}"

        super().__init__(message)


class NetworkNotFoundError(NetworkError):
    """
    Raised when the network with the given name was not found.
    """

    def __init__(
        self,
        network: str,
        ecosystem: Optional[str] = None,
        options: Optional[Collection[str]] = None,
    ):
        self.network = network
        message = (
            f"No network in '{ecosystem}' named '{network}'."
            if ecosystem
            else f"No network named '{network}'."
        )
        if options:
            close_matches = difflib.get_close_matches(network, options, cutoff=0.6)
            if close_matches:
                message = f"{message} Did you mean '{', '.join(close_matches)}'?"
            else:
                # No close matches - show all options.
                options_str = "\n".join(sorted(options))
                message = f"{message} Options:\n{options_str}"

        super().__init__(message)


class ProviderNotFoundError(NetworkError):
    """
    Raised when the provider with the given name was not found.
    """

    def __init__(
        self,
        provider: str,
        network: Optional[str] = None,
        ecosystem: Optional[str] = None,
        options: Optional[Collection[str]] = None,
    ):
        self.provider = provider
        self.network = network
        self.ecosystem = ecosystem
        message = f"No provider named '{provider}'"
        if network:
            message = f"{message} in network '{network}'"
        if ecosystem:
            message = f"{message} in ecosystem '{ecosystem}'"
        if options:
            close_matches = difflib.get_close_matches(provider, options, cutoff=0.6)
            if close_matches:
                message = f"{message} Did you mean '{', '.join(close_matches)}'?"
            else:
                # No close matches. Show all provider options.
                options_str = "\n".join(sorted(options))
                message = f"{message}. Options:\n{options_str}"
        else:
            message = f"{message}."

        super().__init__(message)


class CompilerError(ApeException):
    """
    Raised when unable to compile.
    """


class ProjectError(ApeException):
    """
    Raised when problems occur in a project.
    """


class ApeAttributeError(ProjectError, AttributeError):
    """
    Raised when trying to access items via ``.`` access.
    """


class UnknownVersionError(ProjectError):
    """
    Raised when trying to install an unknown version of a package.
    """

    def __init__(self, version: str, name: str):
        super().__init__(f"Unknown version '{version}' for repo '{name}'.")


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

    def __init__(self, block_id: "BlockID", reason: Optional[str] = None):
        if isinstance(block_id, bytes):
            block_id_str = block_id.hex()
        else:
            block_id_str = str(block_id)

        message = (
            "Missing latest block."
            if block_id == "latest"
            else f"Block with ID '{block_id_str}' not found."
        )
        if reason:
            message = f"{message} Reason: {reason}"

        super().__init__(message)


class TransactionNotFoundError(ProviderError):
    """
    Raised when unable to find a transaction.
    """

    def __init__(self, txn_hash: str, error_messsage: Optional[str] = None):
        message = f"Transaction '{txn_hash}' not found."
        suffix = f" Error: {error_messsage}" if error_messsage else ""
        super().__init__(f"{message}{suffix}")


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


class ContractNotFoundError(ChainError):
    """
    Raised when a contract is not found at an address.
    """

    def __init__(self, address: "AddressType", has_explorer: bool, provider_name: str):
        msg = f"Failed to get contract type for address '{address}'."
        msg += (
            " Contract may need verification."
            if has_explorer
            else (
                f" Current provider '{provider_name}' has no associated "
                "explorer plugin. Try installing an explorer plugin using "
                f"{click.style(text='ape plugins install etherscan', fg='green')}, "
                "or using a network with explorer support."
            )
        )
        super().__init__(msg)


class UnknownSnapshotError(ChainError):
    """
    Raised when given an unknown snapshot ID.
    """

    def __init__(self, snapshot_id: "SnapshotID"):
        if isinstance(snapshot_id, bytes):
            # Is block hash
            snapshot_id = humanize_hash(cast(Hash32, snapshot_id))

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
        err (:class:`~ape.exceptions.TransactionError`): The transaction error
          being handled.
        base_paths (Optional[List[Path]]): Optionally include additional
          source-path prefixes to use when finding relevant frames.

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

        err_type_name = getattr(type(exc), "__name__", "Exception")
        return Abort(f"({err_type_name}) {err_message}")

    def show(self, file=None):
        """
        Override default ``show`` to print CLI errors in red text.
        """

        logger.error(self.format_message())


class CustomError(ContractLogicError):
    """
    An error defined in a smart contract.
    """

    def __init__(
        self,
        abi: ErrorABI,
        inputs: Dict[str, Any],
        txn: Optional[FailedTxn] = None,
        trace: Optional[Iterator["TraceFrame"]] = None,
        contract_address: Optional["AddressType"] = None,
        base_err: Optional[Exception] = None,
        source_traceback: Optional["SourceTraceback"] = None,
    ):
        self.abi = abi
        self.inputs = inputs

        if inputs:
            message = ", ".join(sorted([f"{k}={v}" for k, v in inputs.items()]))
        else:
            # Name of the custom error is all custom info.
            message = TransactionError.DEFAULT_MESSAGE

        super().__init__(
            message,
            base_err=base_err,
            contract_address=contract_address,
            source_traceback=source_traceback,
            trace=trace,
            txn=txn,
        )

    @property
    def name(self) -> str:
        """
        The name of the error.
        """
        return self.abi.name


def _get_ape_traceback(txn: FailedTxn) -> Optional["SourceTraceback"]:
    from ape.api.transactions import ReceiptAPI

    receipt: "ReceiptAPI" = txn if isinstance(txn, ReceiptAPI) else txn.receipt  # type: ignore
    if not receipt:
        return None

    try:
        ape_traceback = receipt.source_traceback
    except (ApeException, NotImplementedError):
        return None

    if ape_traceback is None or not len(ape_traceback):
        return None

    return ape_traceback


def _get_custom_python_traceback(
    err: TransactionError, txn: FailedTxn, ape_traceback: "SourceTraceback"
) -> Optional[TracebackType]:
    # Manipulate python traceback to show lines from contract.
    # Help received from Jinja lib:
    #  https://github.com/pallets/jinja/blob/main/src/jinja2/debug.py#L142

    _, exc_value, tb = sys.exc_info()
    depth = None
    idx = len(ape_traceback) - 1
    frames = []
    project_path = txn.project_manager.path.as_posix()
    while tb is not None:
        if not tb.tb_frame.f_code.co_filename.startswith(project_path):
            # Ignore frames outside the project.
            # This allows both contract code an scripts to appear.
            tb = tb.tb_next
            continue

        frames.append(tb)
        tb = tb.tb_next

    while (depth is None or depth > 1) and idx >= 0:
        exec_item = ape_traceback[idx]
        if depth is not None and exec_item.depth >= depth:
            # Wait for decreasing depth.
            idx -= 1
            continue

        depth = exec_item.depth

        # NOTE: Use the last lineno executed as "the line number".
        lineno = exec_item.begin_lineno if exec_item.end_lineno is None else exec_item.end_lineno

        if lineno is None:
            idx -= 1
            continue

        if exec_item.source_path is None:
            # File is not local. Create a temporary file in its place.
            # This is necessary for tracebacks to work in Python.
            temp_file = tempfile.NamedTemporaryFile(prefix="unknown_contract_")
            filename = temp_file.name
        else:
            filename = exec_item.source_path.as_posix()

        # Raise an exception at the correct line number.
        py_code: CodeType = compile(
            "\n" * (lineno - 1) + "raise __ape_exception__", filename, "exec"
        )
        py_code = py_code.replace(co_name=exec_item.closure.name)

        # Execute the new code to get a new (fake) tb with contract source info.
        try:
            exec(py_code, {"__ape_exception__": err}, {})
        except BaseException:
            real_tb = sys.exc_info()[2]
            fake_tb = getattr(real_tb, "tb_next", None)
            if isinstance(fake_tb, TracebackType):
                frames.append(fake_tb)

        idx -= 1

    if not frames:
        return None

    tb_next = None
    for tb in frames:
        tb.tb_next = tb_next
        tb_next = tb

    return frames[-1]
