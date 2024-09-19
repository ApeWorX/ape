import re

import pytest

from tests.integration.cli.utils import run_once


@run_once
@pytest.mark.parametrize(
    "args",
    [
        (),
        ("--version",),
        ("--config",),
    ],
)
def test_invocation(ape_cli, runner, args):
    result = runner.invoke(ape_cli, args)
    assert result.exit_code == 0, result.output


@run_once
def test_help(ape_cli, runner):
    result = runner.invoke(ape_cli, "--help")
    assert result.exit_code == 0, result.output
    anything = r"[.\n\s\w`/\-,\)\(:\]\[']*"
    expected = (
        rf"{anything}Core Commands:\n  accounts  "
        rf"Manage local accounts{anything}  "
        rf"test\s*Launches pytest{anything}"
    )
    assert re.match(expected.strip(), result.output)
