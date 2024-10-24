from collections.abc import Sequence
from fnmatch import fnmatch
from statistics import mean, median
from typing import TYPE_CHECKING

from rich.box import SIMPLE
from rich.table import Table

from ape.utils.misc import is_evm_precompile, is_zero_hex

if TYPE_CHECKING:
    from ape.types.coverage import CoverageReport
    from ape.types.trace import ContractFunctionPath, GasReport

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
