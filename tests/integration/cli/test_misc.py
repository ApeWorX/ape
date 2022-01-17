import pytest
from github import RateLimitExceededException

from .utils import skip_projects_except


# NOTE: test all the things without a direct test elsewhere
@pytest.mark.parametrize(
    "args",
    (
        [],
        ["--version"],
        ["--config"],
        ["--help"],
        ["accounts"],
        ["networks"],
        ["networks", "list"],
        ["plugins"],
    ),
)
def test_invocation(ape_cli, runner, args):
    result = runner.invoke(ape_cli, args)
    assert result.exit_code == 0, result.output


# Only run these tests once (limited to single arbitrary project).
# This is to prevent Github from rate limiting us and causing test failures.
@skip_projects_except(["empty-config"])
@pytest.mark.parametrize(
    "args",
    (
        ["plugins", "list"],
        ["plugins", "list", "--all"],
    ),
)
def test_invocation_run_once(ape_cli, runner, args):
    result = runner.invoke(ape_cli, args)

    if result.exit_code != 0:
        # Check if failed because we were rate-limited.
        # If that is the case, consider the test as passing.
        err = result.exception
        if not isinstance(err, RateLimitExceededException):
            assert False, result.output

    # Test Passed
