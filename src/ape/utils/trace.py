import fnmatch
import json
import re
from dataclasses import dataclass
from statistics import mean, median
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Type, Union, cast

from eth_abi import decode
from eth_abi.exceptions import InsufficientDataBytes
from eth_typing import Hash32
from eth_utils import humanize_hash, is_hex_address
from ethpm_types import ContractType
from ethpm_types.abi import MethodABI
from evm_trace import CallTreeNode, CallType
from evm_trace.display import TreeRepresentation
from evm_trace.gas import merge_reports
from hexbytes import HexBytes
from rich.box import SIMPLE
from rich.table import Table
from rich.tree import Tree

from ape.exceptions import ContractError, DecodingError
from ape.utils import ManagerAccessMixin
from ape.utils.abi import Struct, parse_type
from ape.utils.misc import ZERO_ADDRESS

if TYPE_CHECKING:
    from ape.api.networks import EcosystemAPI
    from ape.api.transactions import ReceiptAPI
    from ape.types import AddressType, ContractFunctionPath, GasReport


_DEFAULT_TRACE_GAS_PATTERN = re.compile(r"\[\d* gas]")
_DEFAULT_WRAP_THRESHOLD = 50
_DEFAULT_INDENT = 2
_ETH_TRANSFER = "Transferring ETH"


class TraceStyles:
    """
    Colors to use when displaying a call trace.
    Each item in the class points to the part of
    the trace it colors.
    """

    CONTRACTS = "#ff8c00"
    """Contract type names."""

    METHODS = "bright_green"
    """Method names; not including arguments or return values."""

    INPUTS = "bright_magenta"
    """Method arguments."""

    OUTPUTS = "bright_blue"
    """Method return values."""

    DELEGATE = "#d75f00"
    """The part '(delegate)' that appears before delegate calls."""

    VALUE = "#00afd7"
    """The transaction value, when it's > 0."""

    GAS_COST = "dim"
    """The gas used of the call."""


class CallTraceParser(ManagerAccessMixin):
    """
    A class for parsing a call trace, used in the
    :meth:`~ape.api.transactions.ReceiptAPI.show_trace` method,
    which uses the response from
    :meth:`~ape.api.providers.ProviderAPI.get_call_trace` and the
    ``evm-trace`` Python package.

    Usage example::

        parser = CallTraceParser(sender=sender, transaction_hash=txn_hash, verbose=verbose)
        call_tree = self.provider.get_call_tree(txn_hash)
        root = parser.parse_as_tree(call_tree)
    """

    def __init__(
        self,
        sender: Union["ReceiptAPI", Optional["AddressType"]] = None,
        transaction_hash: Optional[str] = None,
        verbose: bool = False,
        wrap_threshold: int = _DEFAULT_WRAP_THRESHOLD,
        indent: int = _DEFAULT_INDENT,
        color_set: Union[TraceStyles, Type[TraceStyles]] = TraceStyles,
    ):
        # NOTE: Supports `ReceiptAPI` for backwards-compatability.
        sender = getattr(sender, "sender", sender)
        transaction_hash = transaction_hash or getattr(sender, "transaction_hash", None)
        self._sender = sender
        self._transaction_hash = transaction_hash
        self._verbose = verbose
        self._wrap_threshold = wrap_threshold
        self._indent = indent
        self.colors = color_set

    @property
    def _ecosystem(self) -> "EcosystemAPI":
        return self.provider.network.ecosystem

    def parse_as_tree(self, call: CallTreeNode) -> Tree:
        """
        Create ``rich.Tree`` containing the nodes in a call trace
        for display purposes.

        Args:
            call (``CallTreeNode``): A node object from the ``evm-trace``
              library.

        Returns:
            ``rich.Tree``: A rich tree from the ``rich`` library.
        """

        address = self.provider.network.ecosystem.decode_address(call.address)

        # Collapse pre-compile address calls
        address_int = int(address, 16)
        if 1 <= address_int <= 9:
            sub_trees = [self.parse_as_tree(c) for c in call.calls]
            if len(sub_trees) == 1:
                return sub_trees[0]

            intermediary_node = Tree(f"{address_int}")
            for sub_tree in sub_trees:
                intermediary_node.add(sub_tree)

            return intermediary_node

        contract_type = self.chain_manager.contracts.get(address)
        selector = call.calldata[:4]
        call_signature = ""

        def _dim_default_gas(call_sig: str) -> str:
            # Add style to default gas block so it matches nodes with contract types
            gas_part = re.findall(_DEFAULT_TRACE_GAS_PATTERN, call_sig)
            if gas_part:
                return f"{call_sig.split(gas_part[0])[0]} [{TraceStyles.GAS_COST}]{gas_part[0]}[/]"

            return call_sig

        if contract_type:
            contract_id = self._get_contract_id(address, contract_type=contract_type)
            method_abi = _get_method_abi(selector, contract_type)

            if method_abi:
                raw_calldata = call.calldata[4:]
                arguments = self.decode_calldata(method_abi, raw_calldata)

                # The revert-message appears at the top of the trace output.
                try:
                    return_value = (
                        self.decode_returndata(method_abi, call.returndata)
                        if not call.failed
                        else None
                    )
                except (DecodingError, InsufficientDataBytes):
                    return_value = "<?>"

                method_id = method_abi.name or f"<{selector.hex()}>"
                call_signature = str(
                    _MethodTraceSignature(
                        contract_id,
                        method_id,
                        arguments,
                        return_value,
                        call.call_type,
                        colors=self.colors,
                        _indent=self._indent,
                        _wrap_threshold=self._wrap_threshold,
                    )
                )
                if call.gas_cost:
                    call_signature += f" [{TraceStyles.GAS_COST}][{call.gas_cost} gas][/]"

                if self._verbose:
                    extra_info = {
                        "address": address,
                        "value": call.value,
                        "gas_limit": call.gas_limit,
                        "call_type": call.call_type.value,
                    }
                    call_signature += f" {json.dumps(extra_info, indent=self._indent)}"
            elif contract_type.name and contract_id == contract_type.name:
                # The case where we know the contract name but couldn't decipher the method ID,
                #  such as an unsupported proxy or fallback.
                call_signature = next(TreeRepresentation.make_tree(call)).title
                call_signature = call_signature.replace(address, contract_id)
                call_signature = _dim_default_gas(call_signature)
        else:
            next_node: Optional[TreeRepresentation] = None
            try:
                # Use default representation
                next_node = next(TreeRepresentation.make_tree(call))
            except StopIteration:
                pass

            if next_node:
                call_signature = _dim_default_gas(next_node.title)

            else:
                # Only for mypy's sake. May never get here.
                call_signature = f"{address}.<{selector.hex()}>"
                if call.gas_cost:
                    call_signature = (
                        f"{call_signature} [{TraceStyles.GAS_COST}][{call.gas_cost} gas][/]"
                    )

        if call.value:
            eth_value = round(call.value / 10**18, 8)
            if eth_value:
                call_signature += f" [{self.colors.VALUE}][{eth_value} value][/]"

        parent = Tree(call_signature, guide_style="dim")
        for sub_call in call.calls:
            parent.add(self.parse_as_tree(sub_call))

        return parent

    def decode_calldata(self, method: MethodABI, raw_data: bytes) -> Dict:
        input_types_str = [i.canonical_type for i in method.inputs]
        input_types = [parse_type(i.dict()) for i in method.inputs]

        try:
            raw_input_values = decode(input_types_str, raw_data)
            input_values = [
                self.decode_value(
                    self._ecosystem.decode_primitive_value(v, t),
                )
                for v, t in zip(raw_input_values, input_types)
            ]
        except (DecodingError, InsufficientDataBytes):
            input_values = ["<?>" for _ in input_types]

        arguments = {}
        index = 0
        for i, v in zip(method.inputs, input_values):
            name = i.name or f"{index}"
            arguments[name] = v
            index += 1

        return arguments

    def decode_returndata(self, method: MethodABI, raw_data: bytes) -> Any:
        values = [self.decode_value(v) for v in self._ecosystem.decode_returndata(method, raw_data)]

        if len(values) == 1:
            return values[0]

        return values

    def decode_value(self, value):
        if isinstance(value, HexBytes):
            try:
                string_value = value.strip(b"\x00").decode("utf8")
                return f"'{string_value}'"
            except UnicodeDecodeError:
                # Truncate bytes if very long.
                if len(value) > 24:
                    return humanize_hash(cast(Hash32, value))

                hex_str = HexBytes(value).hex()
                if is_hex_address(hex_str):
                    return self.decode_value(hex_str)

                return hex_str

        elif isinstance(value, str) and is_hex_address(value):
            return self.decode_address(value)

        elif value and isinstance(value, str):
            # Surround non-address strings with quotes.
            return f'"{value}"'

        elif isinstance(value, (list, tuple)):
            return [self.decode_value(v) for v in value]

        elif isinstance(value, Struct):
            return {k: self.decode_value(v) for k, v in value.items()}

        return value

    def decode_address(self, address: str) -> str:
        if address == ZERO_ADDRESS:
            return "ZERO_ADDRESS"

        elif self._sender is not None and address == self._sender:
            return "tx.origin"

        # Use name of known contract if possible.
        checksum_address = self.provider.network.ecosystem.decode_address(address)
        contract_type = self.chain_manager.contracts.get(checksum_address)
        if contract_type and contract_type.name:
            return contract_type.name

        return checksum_address

    def parse_as_gas_report(self, call: CallTreeNode) -> List[Table]:
        report = self._get_rich_gas_report(call)
        return parse_gas_table(report)

    def _get_contract_id(
        self,
        address: "AddressType",
        contract_type: Optional[ContractType] = None,
        use_symbol: bool = True,
    ) -> str:
        if not contract_type:
            return self._get_contract_id_from_address(address)

        if use_symbol and "symbol" in contract_type.view_methods:
            # Use token symbol as name
            contract = self.chain_manager.contracts.instance_at(
                address, contract_type=contract_type, txn_hash=self._transaction_hash
            )

            try:
                symbol = contract.symbol()
                if symbol and str(symbol).strip():
                    return str(symbol).strip()

            except ContractError:
                pass

        contract_id = contract_type.name
        if contract_id:
            contract_id = contract_id.strip()
            if contract_id:
                return contract_id

        return self._get_contract_id(address)

    def _get_contract_id_from_address(self, address: "AddressType") -> str:
        if address in self.account_manager:
            return _ETH_TRANSFER

        return address

    def _get_rich_gas_report(
        self, calltree: CallTreeNode, exclude: Optional[List["ContractFunctionPath"]] = None
    ) -> "GasReport":
        exclusions = exclude or []
        sub_calls = calltree.calls
        this_method = self._get_rich_gas_report
        exclude_arg = [exclusions for _ in sub_calls]
        address = self.provider.network.ecosystem.decode_address(calltree.address)
        contract_type = self.chain_manager.contracts.get(address)
        selector = calltree.calldata[:4]
        contract_id = self._get_contract_id(address, contract_type=contract_type, use_symbol=False)

        for exclusion in exclusions:
            if exclusion.method_name is not None:
                # Method-related excludes are handled below, even when contract also specified.
                continue

            if fnmatch.fnmatch(contract_id, exclusion.contract_name):
                # Skip this whole contract
                reports = [x for x in map(this_method, sub_calls, exclude_arg)]
                if len(reports) == 1:
                    return reports[0]
                elif len(reports) > 1:
                    return merge_reports(*reports)
                else:
                    return {}

        if contract_id == _ETH_TRANSFER and address in self.account_manager:
            receiver_id = self.account_manager[address].alias or address
            method_id = f"to:{receiver_id}"

        elif contract_id == _ETH_TRANSFER:
            method_id = f"to:{address}"

        elif contract_type:
            # NOTE: Use contract name when possible to distinguish between sources with the same
            #  symbol. Also, ape projects don't permit multiple contract types with the same name.
            method_abi = _get_method_abi(selector, contract_type)
            method_id = method_abi.name if method_abi else selector.hex()

            for exclusion in exclusions:
                if not exclusion.method_name:
                    # Full contract skips handled above.
                    continue

                elif not fnmatch.fnmatch(contract_id, exclusion.contract_name):
                    # Method may match, but contract does not match, so continue.
                    continue

                elif fnmatch.fnmatch(method_id, exclusion.method_name):
                    # Skip this report
                    reports = [r for r in map(this_method, sub_calls, exclude_arg)]
                    if len(reports) == 1:
                        return reports[0]
                    elif len(reports) > 1:
                        return merge_reports(*reports)
                    else:
                        return {}

        else:
            method_id = selector.hex()

        report = {
            contract_id: {method_id: [calltree.gas_cost] if calltree.gas_cost is not None else []}
        }
        reports = [r for r in map(this_method, sub_calls, exclude_arg)]
        if len(reports) >= 1:
            return merge_reports(report, *reports)
        else:
            return report


@dataclass()
class _MethodTraceSignature:
    contract_name: str
    method_name: str
    arguments: Dict
    return_value: Any
    call_type: CallType
    colors: Union[TraceStyles, Type[TraceStyles]] = TraceStyles
    _wrap_threshold: int = _DEFAULT_WRAP_THRESHOLD
    _indent: int = _DEFAULT_INDENT

    def __str__(self) -> str:
        contract = f"[{self.colors.CONTRACTS}]{self.contract_name}[/]"
        method = f"[{TraceStyles.METHODS}]{self.method_name}[/]"
        call_path = f"{contract}.{method}"

        if self.call_type == CallType.DELEGATECALL:
            call_path = f"[orange](delegate)[/] {call_path}"

        arguments_str = self._build_arguments_str()
        signature = f"{call_path}{arguments_str}"

        return_str = self._build_return_str()
        if return_str:
            signature = f"{signature} -> {return_str}"

        return signature

    def _build_arguments_str(self) -> str:
        if not self.arguments:
            return "()"

        return self._dict_to_str(self.arguments, TraceStyles.INPUTS)

    def _build_return_str(self) -> Optional[str]:
        if self.return_value in [None, [], (), {}]:
            return None

        elif isinstance(self.return_value, dict):
            return self._dict_to_str(self.return_value, TraceStyles.OUTPUTS)

        elif isinstance(self.return_value, (list, tuple)):
            return f"[{TraceStyles.OUTPUTS}]{self._list_to_str(self.return_value)}[/]"

        return f"[{TraceStyles.OUTPUTS}]{self.return_value}[/]"

    def _dict_to_str(self, dictionary: Dict, color: str) -> str:
        length = sum([len(str(v)) for v in [*dictionary.keys(), *dictionary.values()]])
        do_wrap = length > self._wrap_threshold

        index = 0
        end_index = len(dictionary) - 1
        kv_str = "(\n" if do_wrap else "("

        for key, value in dictionary.items():
            if do_wrap:
                kv_str += self._indent * " "

            if isinstance(value, (list, tuple)):
                value = self._list_to_str(value, 1 if do_wrap else 0)

            kv_str += (
                f"{key}=[{color}]{value}[/]"
                if key and not key.isnumeric()
                else f"[{color}]{value}[/]"
            )
            if index < end_index:
                kv_str += ", "

            if do_wrap:
                kv_str += "\n"

            index += 1

        return f"{kv_str})"

    def _list_to_str(self, ls: Union[List, Tuple], depth: int = 0) -> str:
        if not isinstance(ls, (list, tuple)) or len(str(ls)) < self._wrap_threshold:
            return str(ls)

        elif ls and isinstance(ls[0], (list, tuple)):
            # List of lists
            sub_lists = [self._list_to_str(i) for i in ls]

            # Use multi-line if exceeds threshold OR any of the sub-lists use multi-line
            extra_chars_len = (len(sub_lists) - 1) * 2
            use_multiline = len(str(sub_lists)) + extra_chars_len > self._wrap_threshold or any(
                ["\n" in ls for ls in sub_lists]
            )

            if not use_multiline:
                # Happens for lists like '[[0], [1]]' that are short.
                return f"[{', '.join(sub_lists)}]"

            value = "[\n"
            num_sub_lists = len(sub_lists)
            index = 0
            spacing = self._indent * " " * 2
            for formatted_list in sub_lists:
                if "\n" in formatted_list:
                    # Multi-line sub list. Append 1 more spacing to each line.
                    indented_item = f"\n{spacing}".join(formatted_list.split("\n"))
                    value = f"{value}{spacing}{indented_item}"
                else:
                    # Single line sub-list
                    value = f"{value}{spacing}{formatted_list}"

                if index < num_sub_lists - 1:
                    value = f"{value},"

                value = f"{value}\n"
                index += 1

            value = f"{value}{self._indent * ' '}]"
            return value

        return self._list_to_multiline_str(ls, depth=depth)

    def _list_to_multiline_str(self, value: Union[List, Tuple], depth: int = 0) -> str:
        spacing = self._indent * " "
        new_val = "[\n"
        num_values = len(value)
        for idx in range(num_values):
            ls_spacing = spacing * (depth + 1)
            new_val += f"{ls_spacing}{value[idx]}"
            if idx < num_values - 1:
                new_val += ","

            new_val += "\n"

        new_val += spacing * depth
        new_val += "]"
        return new_val


def _get_method_abi(selector, contract_type) -> Optional[MethodABI]:
    if selector in contract_type.mutable_methods:
        return contract_type.mutable_methods[selector]
    elif selector in contract_type.view_methods:
        return contract_type.view_methods[selector]

    return None


def parse_gas_table(report: "GasReport") -> List[Table]:
    tables: List[Table] = []

    for contract_id, method_calls in report.items():
        title = f"{contract_id} Gas"
        table = Table(title=title, box=SIMPLE)
        table.add_column("Method")
        table.add_column("Times called", justify="right")
        table.add_column("Min.", justify="right")
        table.add_column("Max.", justify="right")
        table.add_column("Mean", justify="right")
        table.add_column("Median", justify="right")

        has_at_least_1_row = False
        for method_call, gases in method_calls.items():
            if not gases:
                continue

            has_at_least_1_row = True
            table.add_row(
                method_call,
                f"{len(gases)}",
                f"{min(gases)}",
                f"{max(gases)}",
                f"{int(round(mean(gases)))}",
                f"{int(round(median(gases)))}",
            )

        if has_at_least_1_row:
            tables.append(table)

    return tables
