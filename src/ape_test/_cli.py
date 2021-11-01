import sys

import click
import pytest

from ape.cli import network_option


@click.command(
    add_help_option=False,  # NOTE: This allows pass-through to pytest's help
    short_help="Launches pytest and runs the tests for a project",
    context_settings=dict(ignore_unknown_options=True),
)
@network_option(default="ethereum:development:test")
@click.argument("pytest_args", nargs=-1, type=click.UNPROCESSED)
def cli(network, pytest_args):
    if "--network" not in pytest_args:
        pytest_args = [*pytest_args, "--network", network]

    return_code = pytest.main([*pytest_args], ["ape_test"])
    if return_code:
        # only exit with non-zero status to make testing easier
        sys.exit(return_code)
