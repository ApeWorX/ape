import sys

import pytest

from tests.conftest import ApeSubprocessRunner

from .utils import skip_projects_except

BAD_COMMAND = "not-a-name"


@pytest.fixture
def scripts_runner(config):
    class ScriptsSubprocessRunner(ApeSubprocessRunner):
        def __init__(self):
            super().__init__("run", data_folder=config.DATA_FOLDER)

    return ScriptsSubprocessRunner()


@skip_projects_except("script")
def test_run_unknown_script(scripts_runner, integ_project):
    scripts_runner.project = integ_project
    result = scripts_runner.invoke(BAD_COMMAND)
    assert result.exit_code == 2
    assert f"No such command '{BAD_COMMAND}'." in result._completed_process.stderr


@skip_projects_except("script")
def test_run(scripts_runner, integ_project):
    scripts_runner.project = integ_project
    result = scripts_runner.invoke()
    assert result.exit_code == 0, result.output
    # By default, no commands are run
    assert "Super secret script output" not in result.output

    not_part_of_test = ("output_contract_view_methods",)
    scripts = [
        s
        for s in integ_project.scripts_folder.glob("*.py")
        if not s.name.startswith("error") and s.stem not in not_part_of_test
    ]
    for script_file in scripts:
        result = scripts_runner.invoke(script_file.stem)
        assert (
            result.exit_code == 0
        ), f"Unexpected exit code for '{script_file.name}'\n{result.output}"

        if script_file.stem.startswith("_"):
            assert "Super secret script output" not in result.output

        else:
            assert "Super secret script output" in result.output


@skip_projects_except("script")
def test_run_with_verbosity(scripts_runner, integ_project):
    scripts_runner.project = integ_project
    result = scripts_runner.invoke("click", "--verbosity", "DEBUG")
    assert result.exit_code == 0, result.output or result._completed_process.stderr


@skip_projects_except("script")
def test_run_subdirectories(scripts_runner, integ_project):
    scripts_runner.project = integ_project
    result = scripts_runner.invoke()
    assert result.exit_code == 0, result.output
    # By default, no commands are run
    assert "Super secret script output" not in result.output
    subdirectory_scripts = [
        s
        for s in (integ_project.scripts_folder / "subdirectory").rglob("*.py")
        if not s.name.startswith("error")
    ]
    for each in subdirectory_scripts:
        result = scripts_runner.invoke("subdirectory", each.stem)
        assert result.exit_code == 0
        assert "Super secret script output" in result.output


@skip_projects_except("only-script-subdirs")
def test_run_only_subdirs(scripts_runner, integ_project):
    scripts_runner.project = integ_project
    result = scripts_runner.invoke()
    assert result.exit_code == 0, result.output
    # By default, no commands are run
    assert "Super secret script output" not in result.output
    subdirectory_scripts = [
        s
        for s in (integ_project.scripts_folder / "subdirectory").rglob("*.py")
        if not s.name.startswith("error")
    ]
    for each in subdirectory_scripts:
        result = scripts_runner.invoke("subdirectory", each.stem)
        assert result.exit_code == 0, f"Unexpected exit code for '{each.name}'"
        assert "Super secret script output" in result.output


@skip_projects_except("script")
def test_run_when_script_errors(scripts_runner, integ_project):
    scripts_runner.project = integ_project
    scripts = [
        s
        for s in integ_project.scripts_folder.glob("*.py")
        if s.name.startswith("error") and not s.name.endswith("forgot_click.py")
    ]
    for script_file in scripts:
        result = scripts_runner.invoke(
            script_file.stem,
        )
        assert (
            result.exit_code != 0
        ), f"Unexpected exit code for '{script_file.name}'.\n{result.output}"
        assert "Expected exception" in result._completed_process.stderr


@skip_projects_except("script")
def test_run_interactive(scripts_runner, integ_project):
    scripts_runner.project = integ_project
    error_names = ("error_main", "error_cli", "error_no_def")
    scripts = [integ_project.scripts_folder / f"{s}.py" for s in error_names]

    # Show that the variable namespace from the script is available in the console.
    user_input = "local_variable\nape.chain.provider.mine()\nape.chain.blocks.head\nexit\n"

    result = scripts_runner.invoke("--interactive", scripts[0].stem, input=user_input)
    assert result.exit_code == 0, result.output

    # From script: local_variable = "test foo bar"
    assert "test foo bar" in result.output
    assert "timestamp=123123123123123" in result.output


@skip_projects_except("script")
def test_run_custom_provider(scripts_runner, integ_project):
    scripts_runner.project = integ_project
    result = scripts_runner.invoke("deploy", "--network", "ethereum:mainnet:http://127.0.0.1:9545")

    # Show that it attempts to connect
    assert result.exit_code == 1, result.output
    assert "No (supported) node found on 'http://127.0.0.1:9545" in result.output


@skip_projects_except("script")
def test_run_custom_network(scripts_runner, integ_project):
    scripts_runner.project = integ_project
    result = scripts_runner.invoke("deploy", "--network", "http://127.0.0.1:9545")

    # Show that it attempts to connect
    assert result.exit_code == 1, result.output
    assert "No (supported) node found on 'http://127.0.0.1:9545" in result.output


@skip_projects_except("script")
def test_try_run_script_missing_cli_decorator(scripts_runner, integ_project):
    """
    Shows that we cannot run a script defining a `cli()` method without
    it being a click command. The script is not recognized, so you get
    a usage error.
    """
    scripts_runner.project = integ_project
    result = scripts_runner.invoke("error_forgot_click")
    assert "Usage: ape run" in result._completed_process.stderr


@skip_projects_except("with-contracts")
def test_uncaught_tx_err(scripts_runner, integ_project):
    scripts_runner.project = integ_project
    result = scripts_runner.invoke("txerr")
    assert '/scripts/txerr.py", line 12, in main' in result.output
    assert "contract.setNumber(5, sender=account)" in result.output
    assert "ERROR" in result.output
    assert "(ContractLogicError) Transaction failed." in result.output


@skip_projects_except("script")
def test_scripts_module_already_installed(integ_project, scripts_runner, mocker):
    """
    Make sure that if there is for some reason a python module names `scripts`
    installed, it does not interfere with Ape's scripting mechanism.
    """
    scripts_runner.project = integ_project
    mock_scripts = mocker.MagicMock()
    mock_path = mocker.MagicMock()
    mock_path._path = "path/to/scripts"
    mock_scripts.__file__ = None
    mock_scripts.__path__ = mock_path
    sys.modules["scripts"] = mock_scripts
    result = scripts_runner.invoke()
    assert result.exit_code == 0, result.output
    del sys.modules["scripts"]


@skip_projects_except("script")
def test_run_recompiles_if_needed(runner, ape_cli, scripts_runner, integ_project):
    """
    Ensure that when a change is made to a contract,
    when we run a script, it re-compiles the script first.
    """
    scripts_runner.project = integ_project

    # Ensure we begin compiled.
    runner.invoke(ape_cli, ("compile", "--force", "--project", f"{integ_project.path}"))

    # Make a change to the contract.
    contract = integ_project.contracts_folder / "VyperContract.json"
    method_name = integ_project.VyperContract.contract_type.view_methods[0].name
    new_method_name = f"f__{method_name}__"
    new_contract_text = contract.read_text().replace(method_name, new_method_name)
    contract.write_text(new_contract_text, encoding="utf8")

    # Run the script. It better recompile first!
    result = scripts_runner.invoke("output_contract_view_methods")
    assert new_method_name in result.output
