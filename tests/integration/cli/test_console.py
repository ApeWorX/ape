import pytest

from ape import __all__
from tests.integration.cli.utils import skip_projects, skip_projects_except

data_and_project_folders = pytest.mark.parametrize("folder", ["PROJECT_FOLDER", "DATA_FOLDER"])

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


def write_ape_console_extras(project, folder, contents):
    extras_file = getattr(project.config_manager, folder).joinpath("ape_console_extras.py")
    extras_file.write_text(contents)
    return extras_file


@pytest.fixture(autouse=True)
def clean_console_rc_write(project):
    yield

    global_extras = project.config_manager.DATA_FOLDER.joinpath("ape_console_extras.py")
    if global_extras.is_file():
        global_extras.unlink()

    project_extras = project.config_manager.PROJECT_FOLDER.joinpath("ape_console_extras.py")
    if project_extras.is_file():
        project_extras.unlink()


# NOTE: We export `__all__` into the IPython session that the console runs in
@skip_projects("geth")
@pytest.mark.parametrize("item", __all__)
def test_console(ape_cli, runner, item):
    result = runner.invoke(
        ape_cli, ["console", "--embed"], input=f"{item}\nexit\n", catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output
    result = runner.invoke(
        ape_cli,
        ["console", "-v", "debug", "--embed"],
        input=f"{item}\nexit\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects("geth")
@data_and_project_folders
def test_console_extras(project, folder, ape_cli, runner):
    write_ape_console_extras(project, folder, EXTRAS_SCRIPT_1)

    result = runner.invoke(
        ape_cli,
        ["console", "--embed"],
        input="\n".join(["assert A == 1", "exit"]) + "\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output

    result = runner.invoke(
        ape_cli,
        ["console", "--embed"],
        input="\n".join(["assert a() == 1", "exit"]) + "\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects("geth")
@data_and_project_folders
def test_console_init_extras(project, folder, ape_cli, runner):
    write_ape_console_extras(project, folder, EXTRAS_SCRIPT_2)
    result = runner.invoke(
        ape_cli,
        ["console", "--embed"],
        input="print('a:', A)\nassert A == 2\nexit\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects("geth")
@data_and_project_folders
def test_console_init_extras_kwargs(project, folder, ape_cli, runner):
    write_ape_console_extras(project, folder, EXTRAS_SCRIPT_3)

    result = runner.invoke(ape_cli, ["console", "--embed"], input="exit\n", catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects("geth")
@data_and_project_folders
def test_console_init_extras_return(project, folder, ape_cli, runner):
    write_ape_console_extras(project, folder, EXTRAS_SCRIPT_4)

    # Test asserts returned A exists and B is not overwritten
    result = runner.invoke(
        ape_cli,
        ["console", "--embed"],
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
def test_console_import_local_path(project, ape_cli, runner):
    result = runner.invoke(
        ape_cli,
        ["console", "--embed"],
        input="\n".join(["from dependency_in_project_only.importme import import_me", "exit"])
        + "\n",
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects_except("only-dependencies")
def test_console_import_local_path_in_extras_file(project, ape_cli, runner):
    write_ape_console_extras(project, "PROJECT_FOLDER", EXTRAS_SCRIPT_5)

    result = runner.invoke(
        ape_cli,
        ["console", "--embed"],
        input="exit\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects_except("only-dependencies")
def test_console_ape_magic(ape_cli, runner):
    result = runner.invoke(
        ape_cli,
        ["console", "--embed"],
        input="%load_ext ape_console.plugin\n%ape--help\nexit\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects_except("only-dependencies")
def test_console_bal_magic(ape_cli, runner, keyfile_account):
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
        ["console", "--embed"],
        input=f"{cmd_str}\n",
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output
