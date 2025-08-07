from collections.abc import Sequence
from fnmatch import fnmatch
from statistics import mean, median
from typing import TYPE_CHECKING, Any, Optional, Union

from eth_utils import is_0x_prefixed, to_hex
from rich.box import SIMPLE
from rich.table import Table

from ape.utils.misc import is_evm_precompile, is_zero_hex

if TYPE_CHECKING:
    from ape.types.coverage import CoverageReport
    from ape.types.trace import ContractFunctionPath, GasReport

USER_ASSERT_TAG = "USER_ASSERT"
DEFAULT_WRAP_THRESHOLD = 50


def prettify_function(
    method: str,
    calldata: Any,
    contract: Optional[str] = None,
    returndata: Optional[Any] = None,
    stylize: bool = False,
    is_create: bool = False,
    depth: int = 0,
) -> str:
    """
    Prettify the given method call-string to a displayable, prettier string.
    Useful for displaying traces and decoded calls.

    Args:
        method (str): the method call-string to prettify.
        calldata (Any): Arguments to the method.
        contract (str | None): The contract name called.
        returndata (Any): Returned values from the method.
        stylize (bool): ``True`` to use rich styling.
        is_create (bool): Set to ``True`` if creating a contract for better styling.
        depth (int): The depth in the trace (or output) this function gets displayed.

    Returns:
        str
    """
    if "(" in method:
        # Only show short name, not ID name
        # (it is the full signature when multiple methods have the same name).
        method = method.split("(")[0].strip() or method

    if stylize:
        method = f"[{TraceStyles.METHODS}]{method}[/]"
        if contract:
            contract = f"[{TraceStyles.CONTRACTS}]{contract}[/]"

    arguments_str = prettify_inputs(calldata, stylize=stylize)
    if is_create and is_0x_prefixed(arguments_str):
        # Un-enriched CREATE calldata is a massive hex.
        arguments_str = "()"

    signature = f"{method}{arguments_str}"
    if not is_create and returndata not in ((), [], None, {}, ""):
        if return_str := _get_outputs_str(returndata, stylize=stylize, depth=depth):
            signature = f"{signature} -> {return_str}"

    if contract:
        signature = f"{contract}.{signature}"

    return signature


def prettify_inputs(inputs: Any, stylize: bool = False) -> str:
    """
    Prettify the inputs to a function or event (or alike).

    Args:
        inputs (Any): the inputs to prettify.
        stylize (bool): ``True`` to use rich styling.

    Returns:
        str
    """
    color = TraceStyles.INPUTS if stylize else None
    if inputs in ["0x", None, (), [], {}]:
        return "()"

    elif isinstance(inputs, dict):
        return prettify_dict(inputs, color=color)

    elif isinstance(inputs, bytes):
        return to_hex(inputs)

    return f"({inputs})"


def _get_outputs_str(outputs: Any, stylize: bool = False, depth: int = 0) -> Optional[str]:
    if outputs in ["0x", None, (), [], {}]:
        return None

    elif isinstance(outputs, dict):
        color = TraceStyles.OUTPUTS if stylize else None
        return prettify_dict(outputs, color=color)

    elif isinstance(outputs, (list, tuple)):
        return (
            f"[{TraceStyles.OUTPUTS}]{prettify_list(outputs)}[/]"
            if stylize
            else prettify_list(outputs, depth=depth)
        )

    return f"[{TraceStyles.OUTPUTS}]{outputs}[/]" if stylize else str(outputs)


def prettify_list(
    ls: Union[list, tuple],
    depth: int = 0,
    indent: int = 2,
    wrap_threshold: int = DEFAULT_WRAP_THRESHOLD,
) -> str:
    """
    Prettify a list of values for displaying.

    Args:
        ls (list): the list to prettify.
        depth (int): The depth the list appears in a tree structure (for traces).

    Returns:
        str
    """
    if not isinstance(ls, (list, tuple)) or len(str(ls)) < wrap_threshold:
        return str(ls)

    elif ls and isinstance(ls[0], (list, tuple)):
        # List of lists
        sub_lists = [prettify_list(i) for i in ls]

        # Use multi-line if exceeds threshold OR any of the sub-lists use multi-line
        extra_chars_len = (len(sub_lists) - 1) * 2
        use_multiline = len(str(sub_lists)) + extra_chars_len > wrap_threshold or any(
            ["\n" in ls for ls in sub_lists]
        )

        if not use_multiline:
            # Happens for lists like '[[0], [1]]' that are short.
            return f"[{', '.join(sub_lists)}]"

        value = "[\n"
        num_sub_lists = len(sub_lists)
        index = 0
        spacing = indent * " " * 2
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


def prettify_dict(
    dictionary: dict,
    color: Optional[str] = None,
    indent: int = 2,
    wrap_threshold: int = DEFAULT_WRAP_THRESHOLD,
) -> str:
    """
    Prettify a dictionary.

    Args:
        dictionary (dict): The dictionary to prettify.
        color (Optional[str]): The color to use for pretty printing.

    Returns:
        str
    """
    length = sum(len(str(v)) for v in [*dictionary.keys(), *dictionary.values()])
    do_wrap = length > wrap_threshold

    index = 0
    end_index = len(dictionary) - 1
    kv_str = "(\n" if do_wrap else "("

    for key, value in dictionary.items():
        if do_wrap:
            kv_str += indent * " "

        if isinstance(value, (list, tuple)):
            value = prettify_list(value, 1 if do_wrap else 0)

        value_str = f"[{color}]{value}[/]" if color is not None else str(value)
        kv_str += f"{key}={value_str}" if key and not key.isnumeric() else value_str
        if index < end_index:
            kv_str += ", "

        if do_wrap:
            kv_str += "\n"

        index += 1

    return f"{kv_str})"


def _list_to_multiline_str(value: Union[list, tuple], depth: int = 0, indent: int = 2) -> str:
    spacing = indent * " "
    ls_spacing = spacing * (depth + 1)
    joined = ",\n".join([f"{ls_spacing}{v}" for v in value])
    new_val = f"[\n{joined}\n{spacing * depth}]"
    return new_val


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


def parse_gas_table(report: "GasReport") -> list[Table]:
    tables: list[Table] = []

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
) -> list[Table]:
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


def _parse_verbose_coverage(coverage: "CoverageReport", statement: bool = True) -> list[Table]:
    tables = []
    row: tuple[str, ...]
    for project in coverage.projects:
        for src in project.sources:
            for contract in src.contracts:
                title = f"{contract.name} Coverage"
                line_rate = round(contract.line_rate * 100, 2)
                fn_rate = round(contract.function_rate * 100, 2)
                caption = f"line={line_rate}%, func={fn_rate}%"
                table = Table(title=title, box=SIMPLE, caption=caption)
                rows: list[tuple[str, ...]] = []
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
                        rows_corrected.append(row[1:])
                        for subrow in rows:
                            if subrow[0] != row[0]:
                                continue

                            rows_corrected.append(subrow[1:])
                            rows.remove(subrow)

                    else:
                        # Use smaller name (no duplicates).
                        rows_corrected.append((row[0], *row[2:]))

                for tbl_row in sorted(rows_corrected):
                    table.add_row(*tbl_row)

                tables.append(table)

    return tables


def _exclude_gas(
    exclusions: Sequence["ContractFunctionPath"], contract_id: str, method_id: str
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
