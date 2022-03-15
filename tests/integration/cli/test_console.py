import pytest

from ape import __all__
from tests.integration.cli.utils import skip_projects


def no_console_error(result):
    return "NameError" not in result.output and "AssertionError" not in result.output


def destroy_ape_console_extras(project):
    project.config_manager.DATA_FOLDER.joinpath("ape_console_extras.py").unlink(True)
    project.config_manager.PROJECT_FOLDER.joinpath("ape_console_extras.py").unlink(True)


def write_ape_console_extras(project, folder, contents):
    extras_file = getattr(project.config_manager, folder).joinpath("ape_console_extras.py")
    extras_file.write_text(contents)
    return extras_file


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
    destroy_ape_console_extras(project)
    write_ape_console_extras(
        project,
        folder,
        """A = 1
def a():
    return A""",
    )

    result = runner.invoke(
        ape_cli, ["console"], input=f"assert A == 1\nexit\n", catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output

    result = runner.invoke(
        ape_cli, ["console"], input=f"assert a() == 1\nexit\n", catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects(["geth"])
@pytest.mark.parametrize("folder", ["PROJECT_FOLDER", "DATA_FOLDER"])
def test_console_init_extras(project, folder, ape_cli, runner):
    destroy_ape_console_extras(project)
    write_ape_console_extras(
        project,
        folder,
        """A = 1
def ape_init_extras():
    global A
    A = 2""",
    )

    result = runner.invoke(
        ape_cli, ["console"], input=f"print('a:', A)\nassert A == 2\nexit\n", catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output


@skip_projects(["geth"])
@pytest.mark.parametrize("folder", ["PROJECT_FOLDER", "DATA_FOLDER"])
def test_console_init_extras_kwargs(project, folder, ape_cli, runner):
    destroy_ape_console_extras(project)
    write_ape_console_extras(
        project,
        folder,
        """
def ape_init_extras(project):
    assert project""",
    )

    result = runner.invoke(ape_cli, ["console"], input=f"exit\n", catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert no_console_error(result), result.output
