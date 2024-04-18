import json
import sys
from abc import abstractmethod
from enum import Enum
from functools import cached_property
from typing import IO, Any, Dict, Iterable, Iterator, List, Optional, Sequence, Tuple, Union

from eth_abi import decode
from eth_utils import is_0x_prefixed, to_hex
from evm_trace import (
    CallTreeNode,
    CallType,
    ParityTraceList,
    TraceFrame,
    get_calltree_from_geth_call_trace,
    get_calltree_from_geth_trace,
    get_calltree_from_parity_trace,
)
from evm_trace.gas import merge_reports
from hexbytes import HexBytes
from rich.tree import Tree

from ape.api.trace import TraceAPI
from ape.exceptions import ProviderError, TransactionNotFoundError
from ape.logging import logger
from ape.types import ContractFunctionPath, GasReport
from ape.utils import ZERO_ADDRESS, is_evm_precompile, is_zero_hex
from ape.utils.trace import TraceStyles, _exclude_gas
from ape_ethereum._print import extract_debug_logs

_INDENT = 2
_WRAP_THRESHOLD = 50


class TraceApproach(Enum):
    """RPC trace_transaction."""

    """No tracing support; think of EthTester."""
    BASIC = 0

    """RPC 'trace_transaction'."""
    PARITY = 1

    """RPC debug_traceTransaction using tracer='callTracer'."""
    GETH_CALL_TRACER = 2

    """
    RPC debug_traceTransaction using struct-log tracer
    and sophisticated parsing from the evm-trace library.
    NOT RECOMMENDED.
    """
    GETH_STRUCT_LOG_PARSE = 3


class Trace(TraceAPI):
    """
    Set to ``True`` to use an ERC-20's SYMBOL as the contract's identifier.
    Is ``True`` when showing pretty traces without gas tables. When gas is
    involved, Ape must use the ``.name`` as the identifier for all contracts.
    """

    """When None, attempts to deduce."""
    call_trace_approach: Optional[TraceApproach] = None

    _enriched_calltree: Optional[Dict] = None

    def __repr__(self) -> str:
        try:
            return f"{self}"
        except Exception as err:
            # Don't let __repr__ fail.
            logger.debug(f"Problem transaction trace: {err}")
            return "<Trace>"

    def __str__(self) -> str:
        return _call_to_str(self.enriched_calltree)

    def _repr_pretty_(self, *args, **kwargs):
        self.show()

    @property
    @abstractmethod
    def raw_trace_frames(self) -> List[Dict]:
        """
        The raw trace frames.
        """

    @property
    @abstractmethod
    def transaction(self) -> Dict:
        """
        The transaction data (obtained differently on
        calls versus transactions).
        """

    @abstractmethod
    def get_calltree(self) -> CallTreeNode:
        """
        Get an un-enriched call-tree node.
        """

    @cached_property
    def debug_logs(self) -> Iterable[Tuple[Any]]:
        """
        Calls from ``console.log()`` and ``print()`` from a transactions call tree.
        """
        return list(extract_debug_logs(self.get_calltree()))

    @property
    def enriched_calltree(self) -> Dict:
        """
        The fully enriched calltree node.
        """
        if self._enriched_calltree is not None:
            return self._enriched_calltree

        # Side-effect: sets `_enriched_calltree` if using Ethereum node provider.
        self.provider.network.ecosystem.enrich_trace(self)

        if self._enriched_calltree is None:
            # If still None (shouldn't be), set to avoid repeated attempts.
            self._enriched_calltree = {}

        return self._enriched_calltree

    @cached_property
    def return_value(self) -> Any:
        calltree = self.enriched_calltree

        # Check if was cached from enrichment.
        if "return_value" in self.__dict__:
            return self.__dict__["return_value"]

        return calltree.get("unenriched_return_values", calltree.get("returndata"))

    @cached_property
    def revert_message(self) -> Optional[str]:
        try:
            frames = self.raw_trace_frames
        except Exception as err:
            logger.error(f"Failed getting traceback: {err}")
            frames = []

        data = frames[-1] if len(frames) > 0 else {}
        memory = data.get("memory", [])
        if ret := "".join([x[2:] for x in memory[4:]]):
            return HexBytes(ret).hex()

        return None

    """ API Methods """

    def show(self, verbose: bool = False, file: IO[str] = sys.stdout):
        call = self.enriched_calltree
        revert_message = None

        if call.get("failed", False):
            default_message = "reverted without message"
            returndata = HexBytes(call.get("returndata", b""))
            if not to_hex(returndata).startswith(
                "0x08c379a00000000000000000000000000000000000000000000000000000000000000020"
            ):
                revert_message = default_message
            else:
                decoded_result = decode(("string",), returndata[4:])
                if len(decoded_result) == 1:
                    revert_message = f'reverted with message: "{decoded_result[0]}"'
                else:
                    revert_message = default_message

        root = self._get_tree(verbose=verbose)
        console = self.chain_manager._reports._get_console(file=file)
        if txn_hash := getattr(self, "transaction_hash", None):
            # Only works on TransactionTrace (not CallTrace).
            console.print(f"Call trace for [bold blue]'{txn_hash}'[/]")

        if revert_message:
            console.print(f"[bold red]{revert_message}[/]")

        if sender := self.transaction.get("from"):
            console.print(f"tx.origin=[{TraceStyles.CONTRACTS}]{sender}[/]")

        console.print(root)

    def get_gas_report(self, exclude: Optional[Sequence[ContractFunctionPath]] = None) -> GasReport:
        call = self.enriched_calltree
        tx = self.transaction

        # Enrich transfers.
        contract_id = call.get("contract_id", "")
        is_transfer = contract_id.startswith("__") and contract_id.endswith("transfer__")
        if is_transfer and tx.get("to") is not None and tx["to"] in self.account_manager:
            receiver_id = self.account_manager[tx["to"]].alias or tx["to"]
            call["method_id"] = f"to:{receiver_id}"

        elif is_transfer and (receiver := tx.get("to")):
            call["method_id"] = f"to:{receiver}"

        exclusions = exclude or []

        if (
            not call.get("contract_id")
            or not call.get("method_id")
            or _exclude_gas(exclusions, call.get("contract_id", ""), call.get("method_id", ""))
        ):
            return merge_reports(*(c.get_gas_report(exclude) for c in call.get("calls", [])))

        elif not is_zero_hex(call["method_id"]) and not is_evm_precompile(call["method_id"]):
            reports = [
                *[c.get_gas_report(exclude) for c in call.get("calls", [])],
                {
                    call["contract_id"]: {
                        call["method_id"]: (
                            [call.get("gas_cost")] if call.get("gas_cost") is not None else []
                        )
                    }
                },
            ]
            return merge_reports(*reports)

        return merge_reports(*(c.get_gas_report(exclude) for c in call.get("calls", [])))

    def show_gas_report(self, verbose: bool = False, file: IO[str] = sys.stdout):
        gas_report = self.get_gas_report()
        self.chain_manager._reports.show_gas(gas_report, file=file)

    def get_raw_frames(self) -> List[Dict]:
        return self.raw_trace_frames

    def get_raw_calltree(self) -> Dict:
        return self.get_calltree().model_dump(mode="json", by_alias=True)

    """ Shared helpers """

    def _get_tx_calltree_kwargs(self) -> Dict:
        if (receiver := self.transaction.get("to")) and receiver != ZERO_ADDRESS:
            call_type = CallType.CALL
        else:
            call_type = CallType.CREATE
            receiver = self.transaction.get("contract_address")

        return {
            "address": receiver,
            "call_type": call_type,
            "calldata": self.transaction.get("data", b""),
            "gas_cost": self.transaction.get("gasCost"),
            "failed": False,
            "value": self.transaction.get("value", 0),
        }

    def _debug_trace_transaction_struct_logs_to_call(self) -> CallTreeNode:
        init_kwargs = self._get_tx_calltree_kwargs()
        return get_calltree_from_geth_trace(
            (TraceFrame.model_validate(f) for f in self.raw_trace_frames), **init_kwargs
        )

    def _get_tree(self, verbose: bool = False) -> Tree:
        return parse_rich_tree(self.enriched_calltree, verbose=verbose)


class TransactionTrace(Trace):
    transaction_hash: str
    debug_trace_transaction_parameters: Dict = {"enableMemory": True}

    @cached_property
    def raw_trace_frames(self) -> List[Dict]:
        """
        The raw trace ``"structLogs"`` from ``debug_traceTransaction``
        for deeper investigation.
        """
        return list(self._stream_struct_logs())

    @cached_property
    def transaction(self) -> Dict:
        receipt = self.chain_manager.get_receipt(self.transaction_hash)
        data = receipt.transaction.model_dump(mode="json", by_alias=True)
        return {**data, **receipt.model_dump(by_alias=True)}

    def _stream_struct_logs(self) -> Iterator[Dict]:
        parameters = self.debug_trace_transaction_parameters
        yield from self.provider.stream_request(
            "debug_traceTransaction",
            [self.transaction_hash, parameters],
            iter_path="result.item",
        )

    def get_calltree(self) -> CallTreeNode:
        if self.call_trace_approach is TraceApproach.BASIC:
            return self._get_basic_calltree()

        elif self.call_trace_approach is TraceApproach.PARITY:
            return self._trace_transaction()

        elif self.call_trace_approach is TraceApproach.GETH_CALL_TRACER:
            return self._debug_trace_transaction_call_tracer()

        elif self.call_trace_approach is TraceApproach.GETH_STRUCT_LOG_PARSE:
            return self._debug_trace_transaction_struct_logs_to_call()

        elif "erigon" in self.provider.client_version.lower():
            # Based on the client version, we know parity works.
            call = self._trace_transaction()
            self._set_approach(TraceApproach.PARITY)
            return call

        return self._discover_calltrace_approach()

    def _discover_calltrace_approach(self) -> CallTreeNode:
        # NOTE: This method is only called once, if at all.
        #   After discovery, short-circuits to the correct approach.
        #   It tries to create an evm_trace.CallTreeNode using
        #   all the approaches in order from fastest to slowest.

        TA = TraceApproach
        approaches = {
            TA.PARITY: self._trace_transaction,
            TA.GETH_CALL_TRACER: self._debug_trace_transaction_call_tracer,
            TA.GETH_STRUCT_LOG_PARSE: self._debug_trace_transaction_struct_logs_to_call,
            TA.BASIC: self._get_basic_calltree,
        }

        reason = ""
        for approach, fn in approaches.items():
            try:
                call = fn()
            except Exception as err:
                reason = f"{err}"
                continue

            self._set_approach(approach)
            return call

        # Not sure this would happen, as the basic-approach should
        # always work.
        raise ProviderError(f"Unable to create CallTreeNode. Reason: {reason}")

    def _debug_trace_transaction(self, parameters: Optional[Dict] = None) -> Dict:
        parameters = parameters or self.debug_trace_transaction_parameters
        return self.provider.make_request(
            "debug_traceTransaction", [self.transaction_hash, parameters]
        )

    def _debug_trace_transaction_call_tracer(self) -> CallTreeNode:
        parameters = {**self.debug_trace_transaction_parameters, "tracer": "callTracer"}
        data = self._debug_trace_transaction(parameters)
        return get_calltree_from_geth_call_trace(data)

    def _trace_transaction(self) -> CallTreeNode:
        try:
            data = self.provider.make_request("trace_transaction", [self.transaction_hash])
        except ProviderError as err:
            if "transaction not found" in str(err).lower():
                raise TransactionNotFoundError(transaction_hash=self.transaction_hash) from err

            raise  # The ProviderError as-is

        parity_objects = ParityTraceList.model_validate(data)
        return get_calltree_from_parity_trace(parity_objects)

    def _get_basic_calltree(self) -> CallTreeNode:
        init_kwargs = self._get_tx_calltree_kwargs()
        receipt = self.chain_manager.get_receipt(self.transaction_hash)
        init_kwargs["gas_cost"] = receipt.gas_used

        # Figure out the 'returndata' using 'eth_call' RPC.
        tx = receipt.transaction.model_copy(update={"nonce": None})
        return_value = self.provider.send_call(tx, block_id=receipt.block_number)
        init_kwargs["returndata"] = return_value

        return CallTreeNode(**init_kwargs)

    def _set_approach(self, approach: TraceApproach):
        self.call_trace_approach = approach
        if hasattr(self.provider, "_call_trace_approach"):
            self.provider._call_trace_approach = approach


class CallTrace(Trace):
    tx: Dict
    arguments: List[Any] = []

    """debug_traceCall must use the struct-log tracer."""
    call_trace_approach: TraceApproach = TraceApproach.GETH_STRUCT_LOG_PARSE
    supports_debug_trace_call: Optional[bool] = None

    @property
    def raw_trace_frames(self) -> List[Dict]:
        return self._traced_call.get("structLogs", [])

    @property
    def return_value(self) -> Any:
        return self._traced_call.get("returnValue", "")

    @cached_property
    def _traced_call(self) -> Dict:
        if self.supports_debug_trace_call is True:
            return self._debug_trace_call()
        elif self.supports_debug_trace_call is False:
            return {}

        try:
            result = self._debug_trace_call()
        except Exception:
            self._set_supports_trace_call(False)
            return {}

        self._set_supports_trace_call(True)
        return result

    @property
    def transaction(self) -> Dict:
        return self.tx

    def get_calltree(self) -> CallTreeNode:
        calltree = self._debug_trace_transaction_struct_logs_to_call()
        calltree.gas_cost = self._traced_call.get("gas", calltree.gas_cost)
        calltree.failed = self._traced_call.get("failed", calltree.failed)
        return calltree

    def _set_supports_trace_call(self, value: bool):
        self.supports_debug_trace_call = value
        if hasattr(self.provider, "_supports_debug_trace_call"):
            self.provider._supports_debug_trace_call = True

    def _debug_trace_call(self):
        arguments = [self.transaction, *self.arguments]

        # Block ID is required, at least for regular geth nodes.
        if len(arguments) == 1:
            arguments.append("latest")

        return self.provider.make_request("debug_traceCall", arguments)


def parse_rich_tree(call: Dict, verbose: bool = False) -> Tree:
    tree = _create_tree(call, verbose=verbose)
    for sub_call in call["calls"]:
        sub_tree = parse_rich_tree(sub_call, verbose=verbose)
        tree.add(sub_tree)

    return tree


def _call_to_str(call: Dict, stylize: bool = False, verbose: bool = False) -> str:
    contract = str(call.get("contract_id", ""))
    is_create = "CREATE" in call.get("call_type", "")
    method = (
        "__new__"
        if is_create and call["method_id"] and is_0x_prefixed(call["method_id"])
        else str(call.get("method_id") or "")
    )
    if "(" in method:
        # Only show short name, not ID name
        # (it is the full signature when multiple methods have the same name).
        method = method.split("(")[0].strip() or method

    if stylize:
        contract = f"[{TraceStyles.CONTRACTS}]{contract}[/]"
        method = f"[{TraceStyles.METHODS}]{method}[/]"

    call_path = f"{contract}.{method}"

    if call.get("call_type") is not None and call["call_type"].upper() == "DELEGATECALL":
        delegate = "(delegate)"
        if stylize:
            delegate = f"[orange]{delegate}[/]"

        call_path = f"{delegate} {call_path}"

    arguments_str = _get_inputs_str(call.get("calldata"), stylize=stylize)
    if is_create and is_0x_prefixed(arguments_str):
        # Un-enriched CREATE calldata is a massive hex.
        arguments_str = ""

    signature = f"{call_path}{arguments_str}"
    returndata = call.get("returndata", "")

    if not is_create and returndata not in ((), [], None, {}, ""):
        if return_str := _get_outputs_str(returndata, stylize=stylize):
            signature = f"{signature} -> {return_str}"

    if call.get("value"):
        value = str(call["value"])
        if stylize:
            value = f"[{TraceStyles.VALUE}]{value}[/]"

        signature += f" {value}"

    if call.get("gas_cost"):
        gas_value = f"[{call['gas_cost']} gas]"
        if stylize:
            gas_value = f"[{TraceStyles.GAS_COST}]{gas_value}[/]"

        signature += f" {gas_value}"

    if verbose:
        verbose_items = {k: v for k, v in call.items() if type(v) in (int, str, bytes, float)}
        extra = json.dumps(verbose_items, indent=2)
        signature = f"{signature}\n{extra}"

    return signature


def _create_tree(call: Dict, verbose: bool = False) -> Tree:
    signature = _call_to_str(call, stylize=True, verbose=verbose)
    return Tree(signature)


def _get_inputs_str(inputs: Any, stylize: bool = False) -> str:
    color = TraceStyles.INPUTS if stylize else None
    if inputs in ["0x", None, (), [], {}]:
        return "()"

    elif isinstance(inputs, dict):
        return _dict_to_str(inputs, color=color)

    elif isinstance(inputs, bytes):
        return HexBytes(inputs).hex()

    return f"({inputs})"


def _get_outputs_str(outputs: Any, stylize: bool = False) -> Optional[str]:
    if outputs in ["0x", None, (), [], {}]:
        return None

    elif isinstance(outputs, dict):
        color = TraceStyles.OUTPUTS if stylize else None
        return _dict_to_str(outputs, color=color)

    elif isinstance(outputs, (list, tuple)):
        return (
            f"[{TraceStyles.OUTPUTS}]{_list_to_str(outputs)}[/]"
            if stylize
            else _list_to_str(outputs)
        )

    return f"[{TraceStyles.OUTPUTS}]{outputs}[/]" if stylize else str(outputs)


def _dict_to_str(dictionary: Dict, color: Optional[str] = None) -> str:
    length = sum(len(str(v)) for v in [*dictionary.keys(), *dictionary.values()])
    do_wrap = length > _WRAP_THRESHOLD

    index = 0
    end_index = len(dictionary) - 1
    kv_str = "(\n" if do_wrap else "("

    for key, value in dictionary.items():
        if do_wrap:
            kv_str += _INDENT * " "

        if isinstance(value, (list, tuple)):
            value = _list_to_str(value, 1 if do_wrap else 0)

        value_str = f"[{color}]{value}[/]" if color is not None else str(value)
        kv_str += f"{key}={value_str}" if key and not key.isnumeric() else value_str
        if index < end_index:
            kv_str += ", "

        if do_wrap:
            kv_str += "\n"

        index += 1

    return f"{kv_str})"


def _list_to_str(ls: Union[List, Tuple], depth: int = 0) -> str:
    if not isinstance(ls, (list, tuple)) or len(str(ls)) < _WRAP_THRESHOLD:
        return str(ls)

    elif ls and isinstance(ls[0], (list, tuple)):
        # List of lists
        sub_lists = [_list_to_str(i) for i in ls]

        # Use multi-line if exceeds threshold OR any of the sub-lists use multi-line
        extra_chars_len = (len(sub_lists) - 1) * 2
        use_multiline = len(str(sub_lists)) + extra_chars_len > _WRAP_THRESHOLD or any(
            ["\n" in ls for ls in sub_lists]
        )

        if not use_multiline:
            # Happens for lists like '[[0], [1]]' that are short.
            return f"[{', '.join(sub_lists)}]"

        value = "[\n"
        num_sub_lists = len(sub_lists)
        index = 0
        spacing = _INDENT * " " * 2
        for formatted_list in sub_lists:
            if "\n" in formatted_list:
                # Multi-line sub list. Append 1 more spacing to each line.
                indented_item = f"\n{spacing}".join(formatted_list.splitlines())
                value = f"{value}{spacing}{indented_item}"
            else:
                # Single line sub-list
                value = f"{value}{spacing}{formatted_list}"

            if index < num_sub_lists - 1:
                value = f"{value},"

            value = f"{value}\n"
            index += 1

        value = f"{value}]"
        return value

    return _list_to_multiline_str(ls, depth=depth)


def _list_to_multiline_str(value: Union[List, Tuple], depth: int = 0) -> str:
    spacing = _INDENT * " "
    ls_spacing = spacing * (depth + 1)
    joined = ",\n".join([f"{ls_spacing}{v}" for v in value])
    new_val = f"[\n{joined}\n{spacing * depth}]"
    return new_val
