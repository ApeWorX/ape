import json
from statistics import mean, median
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from rich.box import SIMPLE
from rich.table import Table
from rich.tree import Tree

if TYPE_CHECKING:
    from ape.types import CallTreeNode, GasReport

_WRAP_THRESHOLD = 50
_INDENT = 2


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


def parse_rich_tree(call: "CallTreeNode", verbose: bool = False) -> Tree:
    tree = _create_tree(call, verbose=verbose)
    for sub_call in call.calls:
        sub_tree = parse_rich_tree(sub_call, verbose=verbose)
        tree.add(sub_tree)

    return tree


def _create_tree(call: "CallTreeNode", verbose: bool = False) -> Tree:
    signature = parse_as_str(call, stylize=True, verbose=verbose)
    return Tree(signature)


def parse_as_str(call: "CallTreeNode", stylize: bool = False, verbose: bool = False) -> str:
    contract = str(call.contract_id)
    method = str(call.method_id)
    if stylize:
        contract = f"[{TraceStyles.CONTRACTS}]{contract}[/]"
        method = f"[{TraceStyles.METHODS}]{method}[/]"

    call_path = f"{contract}.{method}"

    if call.call_type is not None and call.call_type.upper() == "DELEGATECALL":
        delegate = "(delegate)"
        if stylize:
            delegate = f"[orange]{delegate}[/]"

        call_path = f"{delegate} {call_path}"

    signature = call_path
    arguments_str = _get_inputs_str(call.inputs, stylize=stylize)
    signature = f"{signature}{arguments_str}"

    return_str = _get_outputs_str(call.outputs, stylize=stylize)
    if return_str:
        signature = f"{signature} -> {return_str}"

    if call.value:
        value = str(call.value)
        if stylize:
            value = f"[{TraceStyles.VALUE}]{value}[/]"

        signature += f" {value}"

    if call.gas_cost:
        gas_value = f"[{call.gas_cost} gas]"
        if stylize:
            gas_value = f"[{TraceStyles.GAS_COST}]{gas_value}[/]"

        signature += f" {gas_value}"

    if verbose:
        verbose_items = {k: v for k, v in call.raw.items() if type(v) in (int, str, bytes, float)}
        extra = json.dumps(verbose_items, indent=2)
        signature = f"{signature}\n{extra}"

    return signature


def _get_inputs_str(inputs: Any, stylize: bool = False) -> str:
    color = TraceStyles.INPUTS if stylize else None
    if inputs in ["0x", None, (), [], {}]:
        return "()"

    elif isinstance(inputs, dict):
        return _dict_to_str(inputs, color=color)

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


def _dict_to_str(dictionary: Dict, color: Optional[str] = None) -> str:
    length = sum([len(str(v)) for v in [*dictionary.keys(), *dictionary.values()]])
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

        value = f"{value}{_INDENT * ' '}]"
        return value

    return _list_to_multiline_str(ls, depth=depth)


def _list_to_multiline_str(value: Union[List, Tuple], depth: int = 0) -> str:
    spacing = _INDENT * " "
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
