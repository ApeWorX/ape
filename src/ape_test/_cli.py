import sys

import click
import pytest


@click.command(
    add_help_option=False,  # NOTE: This allows pass-through to pytest's help
    short_help="Launches pytest and runs the tests for a project",
    context_settings=dict(ignore_unknown_options=True),
)
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def cli(pytest_args):
    return_code = pytest.main([*pytest_args], ["ape_test"])
    if return_code:
        # only exit with non-zero status to make testing easier
        sys.exit(return_code)
