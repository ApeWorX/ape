import pytest


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
