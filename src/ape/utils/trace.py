import json
from fnmatch import fnmatch
from statistics import mean, median
from typing import TYPE_CHECKING, Any, Dict, List, Optional, Tuple, Union

from eth_pydantic_types import HexBytes
from eth_utils import is_0x_prefixed
from rich.box import SIMPLE
from rich.table import Table
from rich.tree import Tree

from ape.utils.misc import is_evm_precompile, is_zero_hex

if TYPE_CHECKING:
    from ape.types import CallTreeNode, ContractFunctionPath, CoverageReport, GasReport

_WRAP_THRESHOLD = 50
_INDENT = 2
USER_ASSERT_TAG = "USER_ASSERT"


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
    method = (
        "__new__"
        if call.call_type
        and "CREATE" in call.call_type
        and call.method_id
        and is_0x_prefixed(call.method_id)
        else str(call.method_id or "")
    )
    if "(" in method:
        # Only show short name, not ID name
        # (it is the full signature when multiple methods have the same name).
        method = method.split("(")[0].strip() or method

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
    if call.call_type and "CREATE" in call.call_type and is_0x_prefixed(arguments_str):
        # Unenriched CREATE calldata is a massive hex.
        arguments_str = ""

    signature = f"{signature}{arguments_str}"

    if (
        call.call_type
        and "CREATE" not in call.call_type
        and call.outputs not in ((), [], None, {}, "")
    ):
        if return_str := _get_outputs_str(call.outputs, stylize=stylize):
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

        for method_call, gases in sorted(method_calls.items()):
            if not gases:
                continue

            if not method_call or is_zero_hex(method_call) or is_evm_precompile(method_call):
                continue

            elif method_call == "__new__":
                # Looks better in the gas report.
                method_call = "__init__"

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


def parse_coverage_tables(
    coverage: "CoverageReport", verbose: bool = False, statement: bool = True
) -> List[Table]:
    return (
        _parse_verbose_coverage(coverage, statement=statement)
        if verbose
        else [_parse_coverage_table(coverage, statement=statement)]
    )


def _parse_coverage_table(coverage: "CoverageReport", statement: bool = True) -> Table:
    table = Table(title="Contract Coverage", box=SIMPLE)

    # NOTE: Purposely uses same column names as coveragepy
    table.add_column("Name")
    if statement:
        table.add_column("Stmts", justify="right")
        table.add_column("Miss", justify="right")
        table.add_column("Cover", justify="right")

    table.add_column("Funcs", justify="right")

    for project in coverage.projects:
        for src in sorted(project.sources, key=lambda x: x.source_id.lower()):
            row = (
                (
                    src.source_id,
                    f"{src.lines_valid}",
                    f"{src.miss_count}",
                    f"{round(src.line_rate * 100, 2)}%",
                    f"{round(src.function_rate * 100, 2)}%",
                )
                if statement
                else (src.source_id, f"{round(src.function_rate * 100, 2)}%")
            )
            table.add_row(*row)

    return table


def _parse_verbose_coverage(coverage: "CoverageReport", statement: bool = True) -> List[Table]:
    tables = []
    for project in coverage.projects:
        for src in project.sources:
            for contract in src.contracts:
                title = f"{contract.name} Coverage"
                line_rate = round(contract.line_rate * 100, 2)
                fn_rate = round(contract.function_rate * 100, 2)
                caption = f"line={line_rate}%, func={fn_rate}%"
                table = Table(title=title, box=SIMPLE, caption=caption)
                rows: List[Tuple[str, ...]] = []
                table.add_column("Func", justify="right")

                if statement:
                    table.add_column("Stmts", justify="right")
                    table.add_column("Miss", justify="right")

                table.add_column("Cover", justify="right")
                for fn in contract.functions:
                    if fn.name == "__builtin__" and not statement:
                        # Ignore builtins when statement coverage is not being asked for.
                        # It is impossible to really track.
                        continue

                    if fn.name == "__builtin__":
                        # Create a row per unique type.
                        builtins = {x.tag for x in fn.statements if x.tag}
                        for builtin in builtins:
                            name_chars = [
                                c
                                for c in builtin.lower().strip().replace(" ", "_")
                                if c.isalpha() or c == "_"
                            ]
                            name = f"__{''.join(name_chars).replace('dev_', '')}__"
                            miss = (
                                0
                                if any(s.hit_count > 0 for s in fn.statements if s.tag == builtin)
                                else 1
                            )
                            rows.append(
                                tuple((name, name, "1", f"{miss}", "0.0%" if miss else "100.0%"))
                            )

                    else:
                        row = (
                            (
                                fn.name,
                                fn.full_name,
                                f"{fn.lines_valid}",
                                f"{fn.miss_count}",
                                f"{round(fn.line_rate * 100, 2)}%",
                            )
                            if statement
                            else (fn.name, fn.full_name, "✓" if fn.hit_count > 0 else "x")
                        )
                        rows.append(row)

                # Handle cases where normal names are duplicated.
                # Use full names in this case.
                rows_corrected = []
                while rows:
                    row = rows.pop()
                    if row[0] in [r[0] for r in rows]:
                        # Use full-name for all with same name.
                        rows_corrected.append((row[1:]))
                        for subrow in rows:
                            if subrow[0] != row[0]:
                                continue

                            rows_corrected.append((subrow[1:]))
                            rows.remove(subrow)

                    else:
                        # Use smaller name (no duplicates).
                        rows_corrected.append((row[0], *row[2:]))

                for tbl_row in sorted(rows_corrected):
                    table.add_row(*tbl_row)

                tables.append(table)

    return tables


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


def _exclude_gas(
    exclusions: List["ContractFunctionPath"], contract_id: str, method_id: str
) -> bool:
    for exclusion in exclusions:
        if exclusion.method_name is None and fnmatch(contract_id, exclusion.contract_name):
            # Skip this whole contract. Search contracts from sub-calls.
            return True

        for excl in exclusions:
            if not excl.method_name:
                # Full contract skips handled above.
                continue

            elif not fnmatch(contract_id, excl.contract_name):
                # Method may match, but contract does not match, so continue.
                continue

            elif method_id and fnmatch(method_id, excl.method_name):
                # Skip this report because of the method name exclusion criteria.
                return True

    return False
