import sys
from collections.abc import Iterable
from pathlib import Path
from typing import Any

import click
import pytest
from click import Command

from ape.cli.options import ape_cli_context
from ape.logging import LogLevel, _get_level


def _validate_pytest_args(*pytest_args) -> list[str]:
    threshold = len(pytest_args) - 1
    args_iter = iter(pytest_args)
    valid_args = []
    for idx, argument in enumerate(args_iter):
        if idx >= threshold:
            # If the last arg is -v without a value, it is a valid
            # pytest arg.
            valid_args.append(argument)
            break

        elif argument == "-v":
            # Ensure this is a pytest -v and not ape's -v.
            next_arg = next(args_iter)
            lvl_name = _get_level(next_arg)
            if not _is_ape_loglevel(lvl_name):
                valid_args.append(argument)

        else:
            valid_args.append(argument)

    return valid_args


def _is_ape_loglevel(value: Any) -> bool:
    if isinstance(value, (int, LogLevel)):
        return True

    elif isinstance(value, str):
        return (
            value.upper() in [x.name for x in LogLevel]
            or (value.isnumeric() and int(value) in LogLevel)
            or value.lower().startswith("loglevel.")
        )

    return False


class ApeTestCommand(Command):
    def parse_args(self, ctx, args: list[str]) -> list[str]:
        num_args = len(args)
        for idx, argument in enumerate(args):
            if not argument.startswith("-v"):
                continue
            elif (idx == num_args - 1) or argument in ("-vv", "-vvv"):
                # Definitely for pytest.
                ctx.obj["pytest_verbosity"] = argument
                args = [a for a in args if a != argument]
            else:
                # -v with a following arg; ensure not Ape's.
                next_arg = args[idx + 1]
                if not _is_ape_loglevel(next_arg):
                    ctx.obj["pytest_verbosity"] = "-v"
                    args = [a for a in args if a != argument]

        return super().parse_args(ctx, args)


@click.command(
    add_help_option=False,  # NOTE: This allows pass-through to pytest's help
    short_help="Launches pytest and runs the tests for a project",
    context_settings=dict(ignore_unknown_options=True),
    cls=ApeTestCommand,
)
# NOTE: Using '.value' because more performant.
@ape_cli_context(
    default_log_level=LogLevel.WARNING.value,
)
@click.option(
    "-w",
    "--watch",
    is_flag=True,
    default=False,
    help="Watch for changes to project files and re-run the test suite with the given options.",
)
@click.option(
    "--watch-folders",
    multiple=True,
    type=Path,
    default=[Path("contracts"), Path("tests")],
    help=(
        "Folders to watch for changes using `ape test --watch`."
        " Defaults to `contracts/` and `tests/`"
    ),
)
@click.option(
    "--watch-delay",
    type=float,
    default=0.5,
    help="Delay between polling cycles for `ape test --watch`. Defaults to 0.5 seconds.",
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def cli(cli_ctx, watch, watch_folders, watch_delay, pytest_args):
    pytest_arg_ls = [*pytest_args]
    if pytest_verbosity := cli_ctx.get("pytest_verbosity"):
        pytest_arg_ls.append(pytest_verbosity)

    pytest_arg_ls = _validate_pytest_args(*pytest_arg_ls)
    if watch:
        _run_with_observer(watch_folders, watch_delay, *pytest_arg_ls)

    else:
        return_code = pytest.main([*pytest_arg_ls], ["ape_test"])
        if return_code:
            # only exit with non-zero status to make testing easier
            sys.exit(return_code)


def _run_with_observer(watch_folders: Iterable[Path], watch_delay: float, *pytest_arg_ls: str):
    # Abstracted for testing purposes.
    from ape_test._watch import run_with_observer as run

    run(watch_folders, watch_delay, *pytest_arg_ls)
