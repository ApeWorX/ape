import pytest  # type: ignore


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
        ["plugins", "list"],
        ["plugins", "list", "--all"],
    ),
)
def test_invocation(ape_cli, runner, args):
    result = runner.invoke(ape_cli, args)
    assert result.exit_code == 0
