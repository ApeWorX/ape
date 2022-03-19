import pytest

from ape import __all__
from tests.integration.cli.utils import skip_projects

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


def no_console_error(result):
    return "NameError" not in result.output and "AssertionError" not in result.output


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
@skip_projects(["geth"])
@pytest.mark.parametrize("item", __all__)
def test_console(ape_cli, runner, item):
    result = runner.invoke(ape_cli, ["console"], input=f"{item}\nexit\n", catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output
    result = runner.invoke(
        ape_cli, ["console", "-v", "debug"], input=f"{item}\nexit\n", catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects(["geth"])
@pytest.mark.parametrize("folder", ["PROJECT_FOLDER", "DATA_FOLDER"])
def test_console_extras(project, folder, ape_cli, runner):
    write_ape_console_extras(project, folder, EXTRAS_SCRIPT_1)

    result = runner.invoke(
        ape_cli, ["console"], input="\n".join(["assert A == 1", "exit"]), catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output

    result = runner.invoke(
        ape_cli, ["console"], input="\n".join(["assert a() == 1", "exit"]), catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects(["geth"])
@pytest.mark.parametrize("folder", ["PROJECT_FOLDER", "DATA_FOLDER"])
def test_console_init_extras(project, folder, ape_cli, runner):
    write_ape_console_extras(project, folder, EXTRAS_SCRIPT_2)

    result = runner.invoke(
        ape_cli, ["console"], input="print('a:', A)\nassert A == 2\nexit\n", catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects(["geth"])
@pytest.mark.parametrize("folder", ["PROJECT_FOLDER", "DATA_FOLDER"])
def test_console_init_extras_kwargs(project, folder, ape_cli, runner):
    write_ape_console_extras(project, folder, EXTRAS_SCRIPT_3)

    result = runner.invoke(ape_cli, ["console"], input="exit\n", catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects(["geth"])
@pytest.mark.parametrize("folder", ["PROJECT_FOLDER", "DATA_FOLDER"])
def test_console_init_extras_return(project, folder, ape_cli, runner):
    write_ape_console_extras(project, folder, EXTRAS_SCRIPT_4)

    # Test asserts returned A exists and B is not overwritten
    result = runner.invoke(
        ape_cli,
        ["console"],
        input="\n".join(
            [
                "assert A == 1, 'unexpected A'",
                # symbols from ape_init_extras should apply before file namespace
                "assert B == 2, 'unexpected B'",
                "exit",
            ]
        ),
        catch_exceptions=False,
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output
