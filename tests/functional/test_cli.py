import click
import pytest

from ape.cli import get_user_selected_account, network_option
from ape.exceptions import AccountsError

OUTPUT_FORMAT = "__TEST__{}__"


@pytest.fixture
def network_cmd():
    @click.command()
    @network_option()
    def cmd(network):
        click.echo(OUTPUT_FORMAT.format(network))

    return cmd


def test_get_user_selected_account_no_accounts_found():
    with pytest.raises(AccountsError) as err:
        get_user_selected_account()

    assert "No accounts found." in str(err.value)


def test_get_user_selected_account_one_account(runner, keyfile_account):
    # No input needed when only one account
    with runner.isolation():
        account = get_user_selected_account()

    assert account == keyfile_account


def test_get_user_selected_account_multiple_accounts_requires_input(
    runner, keyfile_account, second_keyfile_account
):
    with runner.isolation(input="0\n"):
        account = get_user_selected_account()

    assert account == keyfile_account


def test_get_user_selected_account_custom_prompt(runner, keyfile_account, second_keyfile_account):
    prompt = "THIS_IS_A_CUSTOM_PROMPT"
    with runner.isolation(input="0\n") as out_streams:
        get_user_selected_account(prompt)
        output = out_streams[0].getvalue().decode()

    assert prompt in output


def test_get_user_selected_account_specify_type(runner, keyfile_account):
    with runner.isolation():
        account = get_user_selected_account(account_type=type(keyfile_account))

    assert account == keyfile_account


def test_get_user_selected_account_unknown_type(runner, keyfile_account):
    with pytest.raises(AccountsError) as err:
        get_user_selected_account(account_type=str)  # type: ignore

    assert "Cannot return accounts with type '<class 'str'>'" in str(err.value)


def test_network_option_default(runner, network_cmd):
    result = runner.invoke(network_cmd)
    assert result.exit_code == 0, result.output
    assert OUTPUT_FORMAT.format("ethereum") in result.output


def test_network_option_specified(runner, network_cmd):
    result = runner.invoke(network_cmd, ["--network", "ethereum:local:test"])
    assert result.exit_code == 0, result.output
    assert OUTPUT_FORMAT.format("ethereum:local:test") in result.output


def test_network_option_unknown(runner, network_cmd):
    result = runner.invoke(network_cmd, ["--network", "UNKNOWN"])
    assert result.exit_code != 0, result.output
    assert "Invalid value for '--network'" in result.output


@pytest.mark.parametrize(
    "network_input",
    (
        "something:else:https://127.0.0.1:4545",
        "something:else:https://127.0.0.1",
        "something:else:http://127.0.0.1:4545",
        "something:else:http://127.0.0.1",
        "something:else:http://foo.bar",
        "something:else:https://foo.bar:8000",
        ":else:https://foo.bar:8000",
        "::https://foo.bar:8000",
        "https://foo.bar:8000",
    ),
)
def test_network_option_adhoc(runner, network_cmd, network_input):
    result = runner.invoke(network_cmd, ["--network", network_input])
    assert result.exit_code == 0, result.output
    assert OUTPUT_FORMAT.format(network_input) in result.output
