import os
import sys
import types

import pytest

from ape_run._cli import run_script_module, use_scripts_sys_path
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
        assert result.exit_code == 0, (
            f"Unexpected exit code for '{script_file.name}'\n{result.output}"
        )

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
        assert result.exit_code != 0, (
            f"Unexpected exit code for '{script_file.name}'.\n{result.output}"
        )
        assert "Expected exception" in result._completed_process.stderr


@skip_projects_except("script")
def test_run_interactive(scripts_runner, integ_project):
    scripts_runner.project = integ_project
    error_names = ("error_main", "error_cli", "error_no_def")
    scripts = [integ_project.scripts_folder / f"{s}.py" for s in error_names]

    # Show that the variable namespace from the script is available in the console.
    user_input = (
        "local_variable\nape.chain.provider.mine()\n"
        "print(f'timestamp={ape.chain.blocks.head.timestamp}')\nexit\n"
    )

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


def _env_with_pythonpath(path) -> dict[str, str]:
    existing = os.environ.get("PYTHONPATH")
    value = f"{path}{os.pathsep}{existing}" if existing else str(path)
    return {"PYTHONPATH": value}


@skip_projects_except("script")
@pytest.mark.parametrize("package_kind", ["regular_package", "single_module", "namespace_shadow"])
def test_run_with_installed_scripts_package(integ_project, scripts_runner, tmp_path, package_kind):
    """
    Regression test for #2012: an installed package/module named `scripts` on sys.path
    must not shadow the project's local `scripts/` directory for CLI, main, or no-def scripts.
    """
    fake_site = tmp_path / "fake_site"
    fake_site.mkdir()

    if package_kind == "regular_package":
        pkg = fake_site / "scripts"
        pkg.mkdir()
        (pkg / "__init__.py").write_text("INSTALLED = True\n", encoding="utf8")
    elif package_kind == "single_module":
        (fake_site / "scripts.py").write_text("INSTALLED = True\n", encoding="utf8")
    else:
        pkg = fake_site / "scripts"
        pkg.mkdir()
        (pkg / "click.py").write_text(
            "raise RuntimeError('Loaded installed scripts.click instead of project script')\n",
            encoding="utf8",
        )
        (pkg / "deploy.py").write_text(
            "raise RuntimeError('Loaded installed scripts.deploy instead of project script')\n",
            encoding="utf8",
        )

    env = _env_with_pythonpath(fake_site)
    scripts_runner.project = integ_project

    # CLI-based script (defines Click `cli`)
    cli_result = scripts_runner.invoke("click", env=env)
    assert cli_result.exit_code == 0, (
        f"{cli_result._completed_process.stdout}\n{cli_result._completed_process.stderr}"
    )
    assert "Super secret script output" in cli_result.output
    assert "Exception while parsing script" not in cli_result.output

    # main()-based script (also performs relative import `from ._utils import deploy`)
    main_result = scripts_runner.invoke("deploy", env=env)
    assert main_result.exit_code == 0, (
        f"{main_result._completed_process.stdout}\n{main_result._completed_process.stderr}"
    )
    assert "Super secret script output" in main_result.output

    # No-def script (same name as stdlib `site`)
    nodef_result = scripts_runner.invoke("site", env=env)
    assert nodef_result.exit_code == 0, (
        f"{nodef_result._completed_process.stdout}\n{nodef_result._completed_process.stderr}"
    )
    assert "Super secret script output" in nodef_result.output


@skip_projects_except("script")
def test_use_scripts_sys_path_restores_preexisting_scripts_module(integ_project, tmp_path):
    """
    When a pre-existing `scripts` package (and submodules) is already imported in sys.modules,
    `use_scripts_sys_path` must isolate the project's scripts during execution and restore the
    original `sys.modules` entries afterward, including when an exception is raised.
    """
    fake_site = tmp_path / "fake_site"
    fake_pkg = fake_site / "scripts"
    fake_pkg.mkdir(parents=True)
    init_py = fake_pkg / "__init__.py"
    init_py.write_text("INSTALLED = True\n", encoding="utf8")

    fake_scripts = types.ModuleType("scripts")
    fake_scripts.__file__ = str(init_py)
    fake_scripts.__path__ = [str(fake_pkg)]
    fake_sub = types.ModuleType("scripts.installed_sub")

    prev_scripts = sys.modules.get("scripts")
    prev_sub = sys.modules.get("scripts.installed_sub")
    sys.modules["scripts"] = fake_scripts
    sys.modules["scripts.installed_sub"] = fake_sub
    try:
        script_path = integ_project.scripts_folder / "click.py"
        with use_scripts_sys_path(integ_project.path):
            ns = run_script_module(script_path)
            assert "cli" in ns

        assert sys.modules.get("scripts") is fake_scripts
        assert sys.modules.get("scripts.installed_sub") is fake_sub

        # Also verify restoration on exception
        with (
            pytest.raises(RuntimeError, match="boom"),
            use_scripts_sys_path(integ_project.path),
        ):
            raise RuntimeError("boom")

        assert sys.modules.get("scripts") is fake_scripts
        assert sys.modules.get("scripts.installed_sub") is fake_sub
    finally:
        if prev_scripts is None:
            sys.modules.pop("scripts", None)
        else:
            sys.modules["scripts"] = prev_scripts
        if prev_sub is None:
            sys.modules.pop("scripts.installed_sub", None)
        else:
            sys.modules["scripts.installed_sub"] = prev_sub


@skip_projects_except("script")
def test_run_parse_error_logged_once(scripts_runner, tmp_path):
    """
    Regression test for #2012 duplicate error logging: a script that fails to parse
    should only log its parse error once per invocation (not once per commands property access).
    """
    proj = tmp_path / "broken_cli_project"
    scripts_dir = proj / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "broken.py").write_text(
        "import click\n"
        "raise ImportError('broken import')\n\n"
        "@click.command()\n"
        "def cli():\n"
        "    pass\n",
        encoding="utf8",
    )
    (scripts_dir / "good.py").write_text("def main():\n    print('GOOD_OK')\n", encoding="utf8")

    class _Proj:
        path = proj

    scripts_runner.project = _Proj()
    help_result = scripts_runner.invoke("--help")
    assert help_result.exit_code == 0, help_result.output
    assert help_result.output.count("Exception while parsing script: broken.py") == 1

    good_result = scripts_runner.invoke("good")
    assert good_result.exit_code == 0, good_result.output
    assert "GOOD_OK" in good_result.output
    assert good_result.output.count("Exception while parsing script: broken.py") == 1


@skip_projects_except("script")
def test_run_cli_lazy_relative_import_and_init_with_installed_scripts(scripts_runner, tmp_path):
    """
    Verify lazy relative imports inside `cli()` and `main()` as well as projects whose
    `scripts/` contains an `__init__.py` work even when a `scripts` package is installed.
    """
    fake_site = tmp_path / "fake_site"
    fake_pkg = fake_site / "scripts"
    fake_pkg.mkdir(parents=True)
    (fake_pkg / "__init__.py").write_text("INSTALLED = True\n", encoding="utf8")

    proj = tmp_path / "custom_project"
    scripts_dir = proj / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "__init__.py").write_text(
        "PROJECT_MARKER = 'from_project_init'\n", encoding="utf8"
    )
    (scripts_dir / "_helper.py").write_text("HELPER_VAL = 'lazy_ok'\n", encoding="utf8")
    (scripts_dir / "lazy_cli.py").write_text(
        "import click\n\n"
        "@click.command()\n"
        "def cli():\n"
        "    from . import PROJECT_MARKER\n"
        "    from ._helper import HELPER_VAL\n"
        "    click.echo(f'{PROJECT_MARKER}:{HELPER_VAL}')\n",
        encoding="utf8",
    )
    (scripts_dir / "lazy_main.py").write_text(
        "def main():\n"
        "    from . import PROJECT_MARKER\n"
        "    from ._helper import HELPER_VAL\n"
        "    print(f'{PROJECT_MARKER}:{HELPER_VAL}')\n",
        encoding="utf8",
    )

    env = _env_with_pythonpath(fake_site)

    class _Proj:
        path = proj

    scripts_runner.project = _Proj()

    cli_res = scripts_runner.invoke("lazy_cli", env=env)
    assert cli_res.exit_code == 0, (
        f"{cli_res._completed_process.stdout}\n{cli_res._completed_process.stderr}"
    )
    assert "from_project_init:lazy_ok" in cli_res.output

    main_res = scripts_runner.invoke("lazy_main", env=env)
    assert main_res.exit_code == 0, (
        f"{main_res._completed_process.stdout}\n{main_res._completed_process.stderr}"
    )
    assert "from_project_init:lazy_ok" in main_res.output


@skip_projects_except("script")
def test_run_help_does_not_execute_scripts_init(scripts_runner, tmp_path):
    """
    `ape run --help` must not eagerly execute `scripts/__init__.py` when no CLI script is loaded.
    """
    proj = tmp_path / "init_side_effect_project"
    scripts_dir = proj / "scripts"
    scripts_dir.mkdir(parents=True)
    (scripts_dir / "__init__.py").write_text(
        "raise RuntimeError('scripts/__init__.py should not run on --help')\n",
        encoding="utf8",
    )
    (scripts_dir / "only_main.py").write_text("def main():\n    pass\n", encoding="utf8")

    class _Proj:
        path = proj

    scripts_runner.project = _Proj()
    result = scripts_runner.invoke("--help")
    assert result.exit_code == 0, result.output
    assert "only_main" in result.output
