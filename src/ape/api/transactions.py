import time
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple, Union

from eth_abi import decode_abi
from eth_abi.exceptions import InsufficientDataBytes
from eth_utils import humanize_hash, is_hex_address, keccak
from ethpm_types import ContractType
from ethpm_types.abi import EventABI, MethodABI
from evm_trace import CallTreeNode, CallType, TraceFrame, get_calltree_from_trace
from hexbytes import HexBytes
from pydantic.fields import Field
from rich.console import Console as RichConsole
from rich.tree import Tree
from tqdm import tqdm  # type: ignore

from ape.api.explorers import ExplorerAPI
from ape.api.networks import EcosystemAPI
from ape.exceptions import TransactionError
from ape.logging import logger
from ape.types import ContractLog, TransactionSignature
from ape.utils import BaseInterfaceModel, Struct, abstractmethod, cached_property, parse_type

if TYPE_CHECKING:
    from ape.contracts import ContractEvent


_METHOD_NAME_TRACE_COLOR = "bright_green"
_ARGUMENT_VALUE_TRACE_COLOR = "bright_magenta"
_RETURN_VALUE_TRACE_COLOR = "bright_blue"
_WRAP_THRESHOLD = 50
_SPACING = "    "


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
    gas_used: int
    gas_limit: int
    gas_price: int
    input_data: str = ""
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

    def raise_for_status(self):
        """
        Handle provider-specific errors regarding a non-successful
        :class:`~api.providers.TransactionStatusEnum`.
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

    @cached_property
    def trace(self) -> Iterator[TraceFrame]:
        """
        The trace of the transaction, if available from your provider.
        NOTE: The first time this property is called, it fetches the
        trace before caching it.
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

    def show_trace(self):
        """
        Display the complete sequence of contracts and methods called during
        the transaction.

        Display format::

            Contract.functionName(arguments) -> (return_value)
        """
        tree_factory = CallTraceTreeFactory(self)
        root_node_kwargs = {
            "gas_cost": self.gas_used,
            "gas_limit": self.gas_limit,
            "address": self.receiver,
            "calldata": self.input_data,
            "value": self.value,
            "call_type": CallType.MUTABLE,
        }
        call_tree = get_calltree_from_trace(self.trace, **root_node_kwargs)
        root = tree_factory.create_tree(call_tree)
        console = RichConsole()
        console.print(f"Call trace for [bold blue]'{self.txn_hash}'[/]")

        if call_tree.failed:
            default_message = "reverted without message"
            if not call_tree.returndata.hex().startswith(
                "0x08c379a00000000000000000000000000000000000000000000000000000000000000020"
            ):
                suffix = default_message
            else:
                decoded_result = decode_abi(("string",), call_tree.returndata[4:])
                if len(decoded_result) == 1:
                    suffix = f'reverted with message: "{decoded_result[0]}"'
                else:
                    suffix = default_message

            console.print(f"🚫 [bold red]{suffix}[/]")

        console.print(root)


class CallTraceTreeFactory:
    def __init__(self, receipt: ReceiptAPI):
        self._receipt = receipt

    @property
    def _ecosystem(self) -> EcosystemAPI:
        return self._receipt.provider.network.ecosystem

    def create_tree(self, call: CallTreeNode) -> Tree:
        address = self._receipt.provider.network.ecosystem.decode_address(call.address)
        contract_type = self._receipt.chain_manager.contracts.get(address)
        call_signature = None
        if contract_type:
            selector = call.calldata[:4].hex()
            method = _get_method_called(selector, contract_type)
            if method:
                arguments = self._decode_calldata(method, call.calldata[4:])

                # If the call failed, the revert message will appear at the top of the printed
                # trace.
                return_value = (
                    self._decode_returndata(method, call.returndata) if not call.failed else None
                )

                call_signature = str(
                    _MethodTraceSignature(contract_type.name, method.name, arguments, return_value)
                )

        call_signature = call_signature or next(call.display_nodes).title  # type: ignore
        parent = Tree(call_signature, guide_style="dim")
        for sub_call in call.calls:
            parent.add(self.create_tree(sub_call))

        return parent

    def _decode_calldata(self, method: MethodABI, raw_data: bytes) -> Dict:
        input_types = [i.canonical_type for i in method.inputs]  # type: ignore

        try:
            raw_input_values = decode_abi(input_types, raw_data)
            input_values = [
                self._decode_value(
                    self._ecosystem.decode_primitive_value(v, parse_type(t)),
                )
                for v, t in zip(raw_input_values, input_types)
            ]
        except InsufficientDataBytes:
            input_values = ["<?>" for _ in input_types]

        arguments = {}
        index = 0
        for i, v in zip(method.inputs, input_values):
            name = i.name or f"{index}"
            arguments[name] = v
            index += 1

        return arguments

    def _decode_returndata(self, method: MethodABI, raw_data: bytes) -> Any:
        values = [
            self._decode_value(v) for v in self._ecosystem.decode_returndata(method, raw_data)
        ]

        if len(values) == 1:
            return values[0]

        return values

    def _decode_value(self, value):
        if isinstance(value, HexBytes):
            try:
                string_value = value.strip(b"\x00").decode("utf8")
                return f"'{string_value}'"
            except UnicodeDecodeError:
                return humanize_hash(value)

        elif isinstance(value, str) and value.startswith("0x"):
            if is_hex_address(value):
                # Use name of known contract if possible.
                contract_type = self._receipt.chain_manager.contracts.get(value)
                if contract_type:
                    return contract_type.name

            return value

        elif isinstance(value, str):
            # Surround non-address strings with quotes.
            return f'"{value}"'

        elif isinstance(value, (list, tuple)):
            return [self._decode_value(v) for v in value]

        elif isinstance(value, Struct):
            return {k: v for k, v in value.items()}

        return value


@dataclass()
class _MethodTraceSignature:
    contract_name: str
    method_name: str
    arguments: Dict
    return_value: Any

    def __str__(self) -> str:
        call_path = f"{self.contract_name}.[{_METHOD_NAME_TRACE_COLOR}]{self.method_name}[/]"
        arguments_str = self._build_arguments_str()
        signature = f"{call_path}{arguments_str}"

        return_str = self._build_return_str()
        if return_str:
            signature = f"{signature} -> {return_str}"

        return signature

    def _build_arguments_str(self) -> str:
        if not self.arguments:
            return "()"

        return _dict_to_str(self.arguments, _ARGUMENT_VALUE_TRACE_COLOR)

    def _build_return_str(self) -> Optional[str]:
        if self.return_value in [None, [], (), {}]:
            return None

        elif isinstance(self.return_value, dict):
            return _dict_to_str(self.return_value, _RETURN_VALUE_TRACE_COLOR)

        elif isinstance(self.return_value, (list, tuple)):
            return f"[{_RETURN_VALUE_TRACE_COLOR}]{_list_to_str(self.return_value)}[/]"

        return f"[{_RETURN_VALUE_TRACE_COLOR}]{self.return_value}"


def _dict_to_str(dictionary: Dict, color: str) -> str:
    length = sum([len(str(v)) for v in [*dictionary.keys(), *dictionary.values()]])
    do_wrap = length > _WRAP_THRESHOLD

    index = 0
    end_index = len(dictionary) - 1
    arguments_str = "(\n" if do_wrap else "("

    for argument, value in dictionary.items():
        if do_wrap:
            arguments_str += _SPACING

        if isinstance(value, (list, tuple)):
            value = _list_to_str(value, 1 if do_wrap else 0)

        arguments_str += (
            f"{argument}=[{color}]{value}[/]"
            if argument and not argument.isnumeric()
            else f"[{color}]{value}[/]"
        )
        if index < end_index:
            arguments_str += ", "

        if do_wrap:
            arguments_str += "\n"

        index += 1

    return f"{arguments_str})"


def _list_to_str(ls: Union[List, Tuple], depth: int = 0) -> str:
    if not isinstance(ls, (list, tuple)) or len(str(ls)) < _WRAP_THRESHOLD:
        return str(ls)

    else:
        value = "[\n"
        num_values = len(ls)
        for index in range(num_values):
            ls_spacing = _SPACING * (depth + 1)
            value += f"{ls_spacing}{ls[index]}"
            if index < num_values - 1:
                value += ","

            value += "\n"

        value += _SPACING * depth
        value += "]"
        return value


def _get_method_called(selector: str, contract_type: ContractType) -> Optional[MethodABI]:
    methods = [*contract_type.mutable_methods, *contract_type.view_methods]
    for method_abi in methods:
        method_selector = "0x" + keccak(method_abi.selector.encode()).hex()[:8]
        if method_selector == selector:
            return method_abi

    return None
