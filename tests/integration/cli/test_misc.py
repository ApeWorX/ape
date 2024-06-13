import os
import re

import pytest

from ape import Project
from tests.conftest import ApeSubprocessRunner
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


@run_once
def test_invalid_config():
    # Using subprocess runner so we re-hit the init of the cmd.
    runner = ApeSubprocessRunner("ape")
    here = os.curdir
    with Project.create_temporary_project() as tmp:
        cfgfile = tmp.path / "ape-config.yaml"
        # Name is invalid!
        cfgfile.write_text("name:\n  {asdf}")

        os.chdir(tmp.path)
        result = runner.invoke("--help")
        os.chdir(here)

        expected = """
Input should be a valid string
-->1: name:
   2:   {asdf}
""".strip()
        assert result.exit_code != 0
        assert expected in result.output
