import sys

import pytest

from ape import Project
from ape.utils import ManagerAccessMixin, create_tempdir
from ape_console._cli import console
from ape_console.plugin import custom_exception_handler


@pytest.fixture(autouse=True)
def mock_console(mocker):
    """Prevent console from actually launching."""
    return mocker.patch("ape_console._cli._launch_console")


@pytest.fixture(autouse=True)
def mock_ape_console_extras(mocker):
    """Prevent actually loading console extras files."""
    return mocker.patch("ape_console._cli.load_console_extras")


def test_console_extras_uses_ape_namespace(mocker, mock_console, mock_ape_console_extras):
    """
    Test that if console is given extras, those are included in the console
    but not as args to the extras files, as those files expect items from the
    default ape namespace.
    """
    accounts_custom = mocker.MagicMock()
    extras = {"accounts": accounts_custom}
    console(extra_locals=extras)

    # Show extras file still load using Ape namespace.
    actual = mock_ape_console_extras.call_args[1]
    assert actual["accounts"] != accounts_custom

    # Show the custom accounts do get used in console.
    assert mock_console.call_args[0][0]["accounts"] == accounts_custom


def test_console_custom_project(mock_console, mock_ape_console_extras):
    with create_tempdir() as path:
        project = Project(path)
        console(project=project)
        actuals = (
            mock_console.call_args[0][0]["project"],  # Launch namespace
            mock_ape_console_extras.call_args[1]["project"],  # extras-load namespace
        )

    for actual in actuals:
        assert actual == project

    # Ensure sys.path was updated correctly.
    assert sys.path[0] == str(project.path)


def test_custom_exception_handler_handles_non_ape_project(mocker):
    """
    If the user has assigned the variable ``project`` to something else
    in their active ``ape console`` session, the exception handler
    **SHOULD NOT** attempt to use its ``.path``.
    """
    session = mocker.MagicMock()
    session.user_ns = {"project": 123}  # Like doing `project = 123` in a console.

    err = Exception()

    handler_patch = mocker.patch("ape_console.plugin.handle_ape_exception")

    # Execute - this was failing before the fix.
    custom_exception_handler(session, None, err, None)

    # We are expecting the local project's path in the handler.
    expected_path = ManagerAccessMixin.local_project.path
    handler_patch.assert_called_once_with(err, [expected_path])
