import os
from pathlib import Path

import click
import pytest
from click.testing import CliRunner

from ape import plugins
from ape.api.scripts import ScriptRunnerAPI
from ape.plugins.pluggy_patch import plugin_manager as pluggy_manager
from ape_run._cli import ScriptCommand


class EchoScriptRunner(ScriptRunnerAPI):
    @property
    def scripts_folder_name(self) -> str:
        return "script"

    def get_command(self, script_path: Path, name: str) -> click.Command:
        @click.command(name=name)
        def run():
            click.echo(f"ran {script_path.name}")

        return run


class EchoScriptRunnerPlugin:
    @plugins.register(plugins.ScriptRunnerPlugin)
    def register_script_runner(self):
        return (".s.sol",), EchoScriptRunner


@pytest.fixture
def echo_script_runner_plugin():
    plugin = EchoScriptRunnerPlugin()
    pluggy_manager.register(plugin, name="echo_scripts")
    yield plugin
    pluggy_manager.unregister(plugin)


@pytest.fixture
def project_with_foreign_scripts(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "hello.py").write_text("def main():\n    print('hello')\n")
    (tmp_path / "scripts" / "Seed.s.sol").write_text("// seed\n")
    (tmp_path / "script").mkdir()
    (tmp_path / "script" / "Deploy.s.sol").write_text("// deploy\n")
    (tmp_path / "script" / "helper.py").write_text("def main():\n    print('helper')\n")
    (tmp_path / "script" / "_Private.s.sol").write_text("// private\n")
    original_cwd = Path.cwd()
    os.chdir(tmp_path)
    yield tmp_path
    os.chdir(original_cwd)


def test_commands_runs_registered_script_runner_extensions(
    echo_script_runner_plugin, project_with_foreign_scripts
):
    script_command = ScriptCommand(name="run")

    commands = script_command.commands

    assert sorted(commands) == ["Deploy", "Seed", "hello"]
    result = CliRunner().invoke(commands["Deploy"])
    assert result.exit_code == 0, result.output
    assert result.output == "ran Deploy.s.sol\n"
    assert script_command.get_command(None, "script/Deploy.s.sol").name == "Deploy"
    assert script_command.get_command(None, "scripts/hello.py").name == "hello"
