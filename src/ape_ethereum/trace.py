import json
import sys
from abc import abstractmethod
from collections import defaultdict, deque
from collections.abc import Iterable, Iterator, Sequence
from enum import Enum
from functools import cached_property
from typing import IO, Any, Optional, Union

from eth_pydantic_types import HexStr
from eth_utils import is_0x_prefixed, to_hex
from ethpm_types import ContractType, MethodABI
from evm_trace import (
    CallTreeNode,
    CallType,
    ParityTraceList,
    TraceFrame,
    create_trace_frames,
    get_calltree_from_geth_call_trace,
    get_calltree_from_geth_trace,
    get_calltree_from_parity_trace,
)
from evm_trace.gas import merge_reports
from hexbytes import HexBytes
from pydantic import field_validator
from rich.tree import Tree

from ape.api.networks import EcosystemAPI
from ape.api.trace import TraceAPI
from ape.api.transactions import TransactionAPI
from ape.exceptions import ContractLogicError, ProviderError, TransactionNotFoundError
from ape.logging import get_rich_console, logger
from ape.types.address import AddressType
from ape.types.trace import ContractFunctionPath, GasReport
from ape.utils.misc import ZERO_ADDRESS, is_evm_precompile, is_zero_hex, log_instead_of_fail
from ape.utils.trace import TraceStyles, _exclude_gas
from ape_ethereum._print import extract_debug_logs

_INDENT = 2
_WRAP_THRESHOLD = 50
_REVERT_PREFIX = "0x08c379a00000000000000000000000000000000000000000000000000000000000000020"


class TraceApproach(Enum):
    """RPC trace_transaction."""

    BASIC = 0
    """No tracing support; think of EthTester."""

    PARITY = 1
    """RPC 'trace_transaction'."""

    GETH_CALL_TRACER = 2
    """RPC debug_traceTransaction using tracer='callTracer'."""

    GETH_STRUCT_LOG_PARSE = 3
    """
    RPC debug_traceTransaction using struct-log tracer
    and sophisticated parsing from the evm-trace library.
    NOT RECOMMENDED.
    """

    @classmethod
    def from_key(cls, key: str) -> "TraceApproach":
        return cls(cls._validate(key))

    @classmethod
    def _validate(cls, key: Any) -> "TraceApproach":
        if isinstance(key, TraceApproach):
            return key
        elif isinstance(key, int) or (isinstance(key, str) and key.isnumeric()):
            return cls(int(key))

        # Check if given a name.
        key = key.replace("-", "_").upper()

        # Allow shorter, nicer values for the geth-struct-log approach.
        if key in ("GETH", "GETH_STRUCT_LOG", "GETH_STRUCT_LOGS"):
            key = "GETH_STRUCT_LOG_PARSE"

        for member in cls:
            if member.name == key:
                return member

        raise ValueError(f"No enum named '{key}'.")


class Trace(TraceAPI):
    """
    Set to ``True`` to use an ERC-20's SYMBOL as the contract's identifier.
    Is ``True`` when showing pretty traces without gas tables. When gas is
    involved, Ape must use the ``.name`` as the identifier for all contracts.
    """

    call_trace_approach: Optional[TraceApproach] = None
    """When None, attempts to deduce."""

    _enriched_calltree: Optional[dict] = None

    def __repr__(self) -> str:
        try:
            return f"{self}"
        except Exception as err:
            # Don't let __repr__ fail.
            logger.debug(f"Problem transaction trace: {err}")
            return "<Trace>"

    def __str__(self) -> str:
        return _call_to_str(self.enriched_calltree)

    @log_instead_of_fail()
    def _repr_pretty_(self, *args, **kwargs):
        self.show()

    @property
    @abstractmethod
    def raw_trace_frames(self) -> Iterator[dict]:
        """
        The raw trace frames.
        """

    @property
    @abstractmethod
    def transaction(self) -> dict:
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
    def debug_logs(self) -> Iterable[tuple[Any]]:
        """
        Calls from ``console.log()`` and ``print()`` from a transactions call tree.
        """
        return list(extract_debug_logs(self.get_calltree()))

    @property
    def enriched_calltree(self) -> dict:
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

        # Add top-level data if missing.
        if not self._enriched_calltree.get("gas_cost"):
            # Happens on calltrees built from structLogs.
            if gas_used := self.transaction.get("gas_used"):
                if "data" in self.transaction:
                    # Subtract base gas costs.
                    # (21_000 + 4 gas per 0-byte and 16 gas per non-zero byte).
                    data_gas = sum(
                        [4 if x == 0 else 16 for x in HexBytes(self.transaction["data"])]
                    )
                    self._enriched_calltree["gas_cost"] = gas_used - 21_000 - data_gas

        return self._enriched_calltree

    @property
    def frames(self) -> Iterator[TraceFrame]:
        yield from create_trace_frames(iter(self.raw_trace_frames))

    @property
    def addresses(self) -> Iterator[AddressType]:
        yield from self.get_addresses_used()

    @cached_property
    def root_contract_type(self) -> Optional[ContractType]:
        if address := self.transaction.get("to"):
            try:
                return self.chain_manager.contracts.get(address)
            except Exception:
                return None

        return None

    @cached_property
    def root_method_abi(self) -> Optional[MethodABI]:
        method_id = self.transaction.get("data", b"")[:10]
        if ct := self.root_contract_type:
            try:
                return ct.methods[method_id]
            except Exception:
                return None

        return None

    @property
    def _ecosystem(self) -> EcosystemAPI:
        if provider := self.network_manager.active_provider:
            return provider.network.ecosystem

        # Default to Ethereum (since we are in that plugin!)
        return self.network_manager.ethereum

    def get_addresses_used(self, reverse: bool = False):
        frames: Iterable
        if reverse:
            frames = list(self.frames)
            frames = frames[::-1] if reverse else frames
        else:
            # Don't need to run whole list.
            frames = self.frames

        for frame in frames:
            if not (addr := frame.address):
                continue

            yield self._ecosystem.decode_address(addr)

    @cached_property
    def return_value(self) -> Any:
        if self._enriched_calltree:
            # Only check enrichment output if was already enriched!
            # Don't enrich ONLY for return value, as that is very bad performance
            # for realistic contract interactions.
            return self._return_value_from_enriched_calltree

        # Barely enrich a calltree for performance reasons
        # (likely not a need to enrich the whole thing).
        calltree = self.get_raw_calltree()
        return self._get_return_value_from_calltree(calltree)

    @cached_property
    def _return_value_from_enriched_calltree(self) -> Any:
        calltree = self.enriched_calltree

        # Check if was cached from enrichment.
        if "return_value" in self.__dict__:
            return self.__dict__["return_value"]

        return self._get_return_value_from_calltree(calltree)

    def _get_return_value_from_calltree(self, calltree: dict) -> tuple[Optional[Any], ...]:
        num_outputs = 1
        if raw_return_data := calltree.get("returndata"):
            if abi := self._get_abi(calltree):
                # Ensure we return a tuple with the correct length, even if fails.
                num_outputs = len(abi.outputs)
                try:
                    return self._ecosystem.decode_returndata(abi, HexBytes(raw_return_data))
                except Exception as err:
                    logger.debug(f"Failed decoding raw returndata: {raw_return_data}. Error: {err}")
                    return tuple([None for _ in range(num_outputs)])

        return tuple([None for _ in range(num_outputs)])

    @cached_property
    def revert_message(self) -> Optional[str]:
        call = self.enriched_calltree
        if not call.get("failed", False):
            return None

        def try_get_revert_msg(c) -> Optional[str]:
            if msg := c.get("revert_message"):
                return msg

            for sub_c in c.get("calls", []):
                if msg := try_get_revert_msg(sub_c):
                    return msg

            return None

        if message := try_get_revert_msg(call):
            return message

        # Enrichment call-tree not available. Attempt looking in trace-frames.
        if revert_str := self._revert_str_from_trace_frames:
            return to_hex(revert_str)

        return None

    @cached_property
    def _last_frame(self) -> Optional[dict]:
        try:
            frame = deque(self.raw_trace_frames, maxlen=1)
        except Exception as err:
            logger.error(f"Failed getting traceback: {err}")
            return None

        return frame[0] if frame else None

    @cached_property
    def _revert_str_from_trace_frames(self) -> Optional[HexBytes]:
        if frame := self._last_frame:
            memory = frame.get("memory", [])
            if ret := "".join([x[2:] for x in memory[4:]]):
                return HexBytes(ret)

        return None

    @cached_property
    def _return_data_from_trace_frames(self) -> Optional[HexBytes]:
        if frame := self._last_frame:
            memory = frame["memory"]
            start_pos = int(frame["stack"][2], 16) // 32
            return HexBytes("".join(memory[start_pos:]))

        return None

    """ API Methods """

    def show(self, verbose: bool = False, file: IO[str] = sys.stdout):
        call = self.enriched_calltree
        approaches_handling_events = (TraceApproach.GETH_STRUCT_LOG_PARSE,)

        failed = call.get("failed", False)
        revert_message = None
        if failed:
            revert_message = self.revert_message
            revert_message = (
                f'reverted with message: "{revert_message}"'
                if revert_message
                else "reverted without message"
            )

        root = self._get_tree(verbose=verbose)
        console = get_rich_console(file=file)
        if txn_hash := getattr(self, "transaction_hash", None):
            # Only works on TransactionTrace (not CallTrace).
            console.print(f"Call trace for [bold blue]'{txn_hash}'[/]")

        if revert_message:
            console.print(f"[bold red]{revert_message}[/]")

        if sender := self.transaction.get("from"):
            console.print(f"tx.origin=[{TraceStyles.CONTRACTS}]{sender}[/]")

        if self.call_trace_approach not in approaches_handling_events and hasattr(
            self._ecosystem, "_enrich_trace_events"
        ):
            # We must manually attach the contract logs.
            # NOTE: With these approaches, we don't know where they appear
            #   in the call-tree so we have to put them at the top.
            if logs := self.transaction.get("logs", []):
                enriched_events = self._ecosystem._enrich_trace_events(logs)
                event_trees = _events_to_trees(enriched_events)
                if event_trees:
                    console.print()
                    self.chain_manager._reports.show_events(event_trees, console=console)
                    console.print()

        # else: the events are already included in the right spots in the call tree.

        console.print(root)

    def get_gas_report(self, exclude: Optional[Sequence[ContractFunctionPath]] = None) -> GasReport:
        call = self.enriched_calltree
        return self._get_gas_report_from_call(call, exclude=exclude)

    def _get_gas_report_from_call(
        self, call: dict, exclude: Optional[Sequence[ContractFunctionPath]] = None
    ) -> GasReport:
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
        calls = call.get("calls", [])
        sub_reports = (self._get_gas_report_from_call(c, exclude=exclusions) for c in calls)

        if (
            not call.get("contract_id")
            or not call.get("method_id")
            or _exclude_gas(exclusions, call.get("contract_id", ""), call.get("method_id", ""))
        ):
            return merge_reports(*sub_reports)

        elif not is_zero_hex(call["method_id"]) and not is_evm_precompile(call["method_id"]):
            report: GasReport = {
                call["contract_id"]: {
                    call["method_id"]: (
                        [int(call["gas_cost"])] if call.get("gas_cost") is not None else []
                    )
                }
            }
            return merge_reports(*sub_reports, report)

        return merge_reports(*sub_reports)

    def show_gas_report(self, verbose: bool = False, file: IO[str] = sys.stdout):
        gas_report = self.get_gas_report()
        self.chain_manager._reports.show_gas(gas_report, file=file)

    def get_raw_frames(self) -> Iterator[dict]:
        yield from self.raw_trace_frames

    def get_raw_calltree(self) -> dict:
        return self.get_calltree().model_dump(mode="json", by_alias=True)

    """ Shared helpers """

    def _get_tx_calltree_kwargs(self) -> dict:
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
        return get_calltree_from_geth_trace(self.frames, **init_kwargs)

    def _get_tree(self, verbose: bool = False) -> Tree:
        return parse_rich_tree(self.enriched_calltree, verbose=verbose)

    def _get_abi(self, call: dict) -> Optional[MethodABI]:
        if not (addr := call.get("address")):
            return self.root_method_abi
        if not (calldata := call.get("calldata")):
            return self.root_method_abi
        if not (contract_type := self.chain_manager.contracts.get(addr)):
            return self.root_method_abi
        if not (calldata[:10] in contract_type.methods):
            return self.root_method_abi

        return contract_type.methods[calldata[:10]]


class TransactionTrace(Trace):
    transaction_hash: HexStr
    debug_trace_transaction_parameters: dict = {"enableMemory": True}
    _frames: list[dict] = []

    @property
    def raw_trace_frames(self) -> Iterator[dict]:
        """
        The raw trace ``"structLogs"`` from ``debug_traceTransaction``
        for deeper investigation.
        """
        if self._frames:
            yield from self._frames

        else:
            for frame in self._stream_struct_logs():
                self._frames.append(frame)
                yield frame

    @cached_property
    def transaction(self) -> dict:
        receipt = self.chain_manager.get_receipt(self.transaction_hash)
        data = receipt.transaction.model_dump(mode="json", by_alias=True)
        return {**data, **receipt.model_dump(by_alias=True)}

    def _stream_struct_logs(self) -> Iterator[dict]:
        parameters = self.debug_trace_transaction_parameters
        yield from self.provider.stream_request(
            "debug_traceTransaction",
            [self.transaction_hash, parameters],
            iter_path="result.structLogs.item",
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

        reason_map = {}
        for approach, fn in approaches.items():
            try:
                call = fn()
            except Exception as err:
                reason_map[approach.name] = f"{err}"
                continue

            self._set_approach(approach)
            return call

        # Not sure this would happen, as the basic-approach should
        # always work.
        reason_str = ", ".join(f"{k}={v}" for k, v in reason_map.items())
        raise ProviderError(f"Unable to create CallTreeNode. Reason(s): {reason_str}")

    def _debug_trace_transaction(self, parameters: Optional[dict] = None) -> dict:
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
        try:
            return_value = self.provider.send_call(tx, block_id=receipt.block_number)
        except ContractLogicError:
            # Unable to get the return value because even as a call, it fails.
            pass
        else:
            init_kwargs["returndata"] = return_value

        return CallTreeNode(**init_kwargs)

    def _set_approach(self, approach: TraceApproach):
        self.call_trace_approach = approach
        if hasattr(self.provider, "_call_trace_approach"):
            self.provider._call_trace_approach = approach


class CallTrace(Trace):
    tx: dict
    """
    Transaction data. Is a dictionary to allow traces to easily
    be created near sending the request.
    """

    arguments: list[Any] = []
    """
    Remaining eth-call arguments, minus the transaction.
    """

    call_trace_approach: TraceApproach = TraceApproach.GETH_STRUCT_LOG_PARSE
    """debug_traceCall must use the struct-log tracer."""

    supports_debug_trace_call: Optional[bool] = None

    @field_validator("tx", mode="before")
    @classmethod
    def _tx_to_dict(cls, value):
        if isinstance(value, TransactionAPI):
            return value.model_dump(by_alias=True)

        return value

    @property
    def raw_trace_frames(self) -> Iterator[dict]:
        yield from self._traced_call.get("structLogs", [])

    @property
    def return_value(self) -> Any:
        return self._traced_call.get("returnValue", "")

    @cached_property
    def _traced_call(self) -> dict:
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
    def transaction(self) -> dict:
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


def parse_rich_tree(call: dict, verbose: bool = False) -> Tree:
    tree = _create_tree(call, verbose=verbose)
    for event in call.get("events", []):
        if "calldata" not in event and "name" not in event:
            # Not sure; or not worth showing.
            logger.debug(f"Unknown event data: '{event}'.")
            continue

        event_tree = _create_event_tree(event)
        tree.add(event_tree)

    for sub_call in call.get("calls", []):
        sub_tree = parse_rich_tree(sub_call, verbose=verbose)
        tree.add(sub_tree)

    return tree


def _events_to_trees(events: list[dict]) -> list[Tree]:
    event_counter = defaultdict(list)
    for evt in events:
        name = evt.get("name")
        calldata = evt.get("calldata")

        if not name or not calldata:
            # Not sure; or not worth showing.
            logger.debug(f"Unknown event data: '{evt}'.")
            continue

        tuple_key = (
            name,
            ",".join(f"{k}={v}" for k, v in calldata.items()),
        )
        event_counter[tuple_key].append(evt)

    result = []
    for evt_tup, events in event_counter.items():
        count = len(events)
        evt = events[0]
        if "name" not in evt and "calldata" not in evt:
            # Not sure; or not worth showing.
            logger.debug(f"Unknown event data: '{evt}'.")
            continue

        # NOTE: Using similar style to gas-cost on purpose.
        suffix = f"[[{TraceStyles.GAS_COST}]x{count}[/]]" if count > 1 else ""
        evt_tree = _create_event_tree(evt, suffix=suffix)
        result.append(evt_tree)

    return result


def _create_event_tree(event: dict, suffix: str = "") -> Tree:
    signature = _event_to_str(event, stylize=True, suffix=suffix)
    return Tree(signature)


def _call_to_str(call: dict, stylize: bool = False, verbose: bool = False) -> str:
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


def _event_to_str(event: dict, stylize: bool = False, suffix: str = "") -> str:
    # NOTE: Some of the styles are matching others parts of the trace,
    #  even though the 'name' is a bit misleading.
    event_name = event.get("name", "ANONYMOUS_EVENT")
    name = f"[{TraceStyles.METHODS}]{event_name}[/]" if stylize else event_name
    arguments_str = _get_inputs_str(event.get("calldata", "0x"), stylize=stylize)
    prefix = f"[{TraceStyles.CONTRACTS}]log[/]" if stylize else "log"
    return f"{prefix} {name}{arguments_str}{suffix}"


def _create_tree(call: dict, verbose: bool = False) -> Tree:
    signature = _call_to_str(call, stylize=True, verbose=verbose)
    return Tree(signature)


def _get_inputs_str(inputs: Any, stylize: bool = False) -> str:
    color = TraceStyles.INPUTS if stylize else None
    if inputs in ["0x", None, (), [], {}]:
        return "()"

    elif isinstance(inputs, dict):
        return _dict_to_str(inputs, color=color)

    elif isinstance(inputs, bytes):
        return to_hex(inputs)

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


def _dict_to_str(dictionary: dict, color: Optional[str] = None) -> str:
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


def _list_to_str(ls: Union[list, tuple], depth: int = 0) -> str:
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


def _list_to_multiline_str(value: Union[list, tuple], depth: int = 0) -> str:
    spacing = _INDENT * " "
    ls_spacing = spacing * (depth + 1)
    joined = ",\n".join([f"{ls_spacing}{v}" for v in value])
    new_val = f"[\n{joined}\n{spacing * depth}]"
    return new_val
