from pathlib import Path

import pytest

from ape import __all__
from tests.integration.cli.utils import skip_projects, skip_projects_except


@pytest.fixture(params=("path", "root"))
def extras_base_path(integ_project, request):
    if request.param == "path":
        yield integ_project.path
    else:
        yield integ_project.config_manager.DATA_FOLDER


# Simple single namespace example
EXTRAS_SCRIPT_1 = """
A = 1
def a():
    return A
"""

# Tests ape_init_extras function alters namespace
EXTRAS_SCRIPT_2 = """
A = 1

def ape_init_extras():
    global A
    A = 2
"""

# Tests that namespace kwargs are available
EXTRAS_SCRIPT_3 = """
def ape_init_extras(project):
    assert project
"""

# Tests that returned dict is added to namespace
EXTRAS_SCRIPT_4 = """
B = 4

def ape_init_extras():
    return {"A": 1, "B": 2}
"""

# Tests that we can import a local package
EXTRAS_SCRIPT_5 = """
from dependency_in_project_only.importme import import_me

import_me()
"""


def no_console_error(result):
    return (
        "NameError" not in result.output
        and "AssertionError" not in result.output
        and "ModuleNotFoundError" not in result.output
    )


def write_ape_console_extras(base_path, contents):
    extras_file = base_path.joinpath("ape_console_extras.py")
    extras_file.write_text(contents, encoding="utf8")
    return extras_file


@pytest.fixture(autouse=True)
def clean_console_rc_write(project):
    yield

    global_extras = project.config_manager.DATA_FOLDER.joinpath("ape_console_extras.py")
    if global_extras.is_file():
        global_extras.unlink()

    project_extras = project.path.joinpath("ape_console_extras.py")
    if project_extras.is_file():
        project_extras.unlink()


# NOTE: We export `__all__` into the IPython session that the console runs in
@skip_projects("geth")
@pytest.mark.parametrize("item", __all__)
def test_console(ape_cli, runner, item, project):
    arguments = ["console", "--project", f"{project.path}"]
    result = runner.invoke(ape_cli, arguments, input=f"{item}\nexit\n", catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output
    arguments.extend(("-v", "debug"))
    result = runner.invoke(
        ape_cli,
        arguments,
        input=f"{item}\nexit\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects("geth")
def test_console_extras(integ_project, extras_base_path, ape_cli, runner):
    write_ape_console_extras(extras_base_path, EXTRAS_SCRIPT_1)
    arguments = ("console", "--project", f"{integ_project.path}")

    result = runner.invoke(
        ape_cli,
        arguments,
        input="\n".join(["assert A == 1", "exit"]) + "\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output

    result = runner.invoke(
        ape_cli,
        arguments,
        input="\n".join(["assert a() == 1", "exit"]) + "\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects("geth")
def test_console_init_extras(integ_project, extras_base_path, ape_cli, runner):
    write_ape_console_extras(extras_base_path, EXTRAS_SCRIPT_2)
    arguments = ("console", "--project", f"{integ_project.path}")
    result = runner.invoke(
        ape_cli,
        arguments,
        input="print('a:', A)\nassert A == 2\nexit\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects("geth")
def test_console_init_extras_kwargs(integ_project, extras_base_path, ape_cli, runner):
    write_ape_console_extras(extras_base_path, EXTRAS_SCRIPT_3)
    arguments = ("console", "--project", f"{integ_project.path}")
    result = runner.invoke(ape_cli, arguments, input="exit\n", catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects("geth")
def test_console_init_extras_return(integ_project, extras_base_path, ape_cli, runner):
    write_ape_console_extras(extras_base_path, EXTRAS_SCRIPT_4)
    arguments = ("console", "--project", f"{integ_project.path}")

    # Test asserts returned A exists and B is not overwritten
    result = runner.invoke(
        ape_cli,
        arguments,
        input="\n".join(
            [
                "assert A == 1, 'unexpected A'",
                # symbols from ape_init_extras should apply before file namespace
                "assert B == 2, 'unexpected B'",
                "exit",
            ]
        )
        + "\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects_except("only-dependencies")
def test_console_import_local_path(integ_project, ape_cli, runner):
    # NOTE: Don't use temp-path! Temp-path projects do not copy Python modules.
    path = Path(__file__).parent / "projects" / "only-dependencies"
    arguments = ("console", "--project", f"{path}")
    result = runner.invoke(
        ape_cli,
        arguments,
        input="\n".join(["from dependency_in_project_only.importme import import_me", "exit"])
        + "\n",
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects_except("only-dependencies")
def test_console_import_local_path_in_extras_file(integ_project, extras_base_path, ape_cli, runner):
    # NOTE: Don't use tmp path! Temp projects do not copy Python modules.
    path = Path(__file__).parent / "projects" / "only-dependencies"
    write_ape_console_extras(extras_base_path, EXTRAS_SCRIPT_5)
    arguments = ("console", "--project", f"{path}")
    result = runner.invoke(
        ape_cli,
        arguments,
        input="exit\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects_except("only-dependencies")
def test_console_ape_magic(integ_project, ape_cli, runner):
    arguments = ("console", "--project", f"{integ_project.path}")
    result = runner.invoke(
        ape_cli,
        arguments,
        input="%load_ext ape_console.plugin\n%ape--help\nexit\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects_except("only-dependencies")
def test_console_bal_magic(integ_project, ape_cli, runner, keyfile_account):
    arguments = ("console", "--project", f"{integ_project.path}")
    cases = (
        "%load_ext ape_console.plugin",
        "%bal acct",
        "%bal acct.alias",
        "%bal acct.address",
        "%bal int(acct.address, 16)",
    )
    cmd_ls = [f"acct = accounts.load('{keyfile_account.alias}')", *cases, "exit"]
    cmd_str = "\n".join(cmd_ls)
    result = runner.invoke(
        ape_cli,
        arguments,
        input=f"{cmd_str}\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects_except("with-contracts")
def test_uncaught_txn_err(integ_project, ape_cli, runner, mocker):
    # For some reason, not showing in result.output, so captured another way.
    handler = mocker.patch("ape_console.plugin.handle_ape_exception")
    cmd_ls = [
        "%load_ext ape_console.plugin",
        "account = accounts.test_accounts[0]",
        "contract = account.deploy(project.ContractA)",
        "receipt = contract.setNumber(5, sender=account)",
        "print(receipt)",
        "exit",
    ]
    cmd_str = "\n".join(cmd_ls)
    arguments = ("console", "--project", f"{integ_project.path}")
    runner.invoke(
        ape_cli,
        arguments,
        input=f"{cmd_str}\n",
        catch_exceptions=False,
    )
    err = handler.call_args[0][0]
    assert str(err) == "Transaction failed."


def test_console_none_network(integ_project, ape_cli, runner):
    arguments = ("console", "--project", f"{integ_project.path}", "--network", "None")
    result = runner.invoke(ape_cli, arguments, input="exit\n", catch_exceptions=False)
    assert result.exit_code == 0
