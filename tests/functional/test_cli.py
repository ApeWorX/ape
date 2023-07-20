import shutil

import click
import pytest

from ape.cli import (
    AccountAliasPromptChoice,
    NetworkBoundCommand,
    PromptChoice,
    account_option,
    contract_file_paths_argument,
    get_user_selected_account,
    network_option,
    verbosity_option,
)
from ape.exceptions import AccountsError
from ape.logging import logger

OUTPUT_FORMAT = "__TEST__{}__"


@pytest.fixture
def keyfile_swap_paths(config):
    return config.DATA_FOLDER / "accounts", config.DATA_FOLDER.parent / "temp_accounts"


@pytest.fixture
def one_keyfile_account(keyfile_swap_paths, keyfile_account, temp_config):
    src_path, dest_path = keyfile_swap_paths
    existing_keyfiles = [x for x in src_path.iterdir() if x.is_file()]
    test_data = {"test": {"number_of_accounts": 0}}
    if existing_keyfiles == [keyfile_account.keyfile_path]:
        # Already only has the 1 account
        with temp_config(test_data):
            yield keyfile_account

    else:
        if dest_path.is_file():
            dest_path.unlink()
        elif dest_path.is_dir():
            shutil.rmtree(dest_path)

        dest_path.mkdir()
        for keyfile in [x for x in existing_keyfiles if x != keyfile_account.keyfile_path]:
            shutil.copy(keyfile, dest_path / keyfile.name)
            keyfile.unlink()

        with temp_config(test_data):
            yield keyfile_account

        for file in dest_path.iterdir():
            shutil.copy(file, src_path / file.name)


@pytest.fixture
def network_cmd():
    @click.command()
    @network_option()
    def cmd(network):
        click.echo(OUTPUT_FORMAT.format(network))

    return cmd


def _setup_temp_acct_number_change(accounts, num_accounts: int):
    if "containers" in accounts.__dict__:
        del accounts.__dict__["containers"]

    installed_account_types = {str(type(a)) for a in accounts}
    if installed_account_types:
        accounts_str = ", ".join(installed_account_types)
        pytest.fail(f"Unable to side-step install of account type(s): {accounts_str}")

    return {"test": {"number_of_accounts": num_accounts}}


def _teardown_numb_acct_change(accounts):
    if "containers" in accounts.__dict__:
        del accounts.__dict__["containers"]


@pytest.fixture
def no_accounts(accounts, empty_data_folder, temp_config):
    data = _setup_temp_acct_number_change(accounts, 0)
    with temp_config(data):
        yield

    _teardown_numb_acct_change(accounts)


@pytest.fixture
def one_account(accounts, empty_data_folder, temp_config, test_accounts):
    data = _setup_temp_acct_number_change(accounts, 1)
    with temp_config(data):
        yield test_accounts[0]

    _teardown_numb_acct_change(accounts)


def get_expected_account_str(acct):
    return f"__expected_output__: {acct.address}"


def test_get_user_selected_account_no_accounts_found(no_accounts):
    with pytest.raises(AccountsError, match="No accounts found."):
        assert not get_user_selected_account()


def test_get_user_selected_account_one_account(runner, one_account):
    # No input needed when only one account
    with runner.isolation():
        account = get_user_selected_account()

    assert account == one_account


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


def test_get_user_selected_account_specify_type(runner, one_keyfile_account):
    with runner.isolation():
        account = get_user_selected_account(account_type=type(one_keyfile_account))

    assert account == one_keyfile_account


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


def test_network_option_make_required(runner):
    @click.command()
    @network_option(required=True)
    def cmd(network):
        click.echo(OUTPUT_FORMAT.format(network))

    result = runner.invoke(cmd, [])
    assert result.exit_code == 2
    assert "Error: Missing option '--network'." in result.output


def test_network_option_can_be_none(runner):
    @click.command()
    @network_option(default=None)
    def cmd(network):
        click.echo(f"Value is '{network}'")

    result = runner.invoke(cmd, [])
    assert "Value is 'None'" in result.output


def test_network_option_not_needed_on_network_bound_command(runner):
    @click.command(cls=NetworkBoundCommand)
    def cmd():
        click.echo("Success!")

    result = runner.invoke(cmd, [])
    assert "Success" in result.output


def test_account_option(runner, keyfile_account):
    @click.command()
    @account_option()
    def cmd(account):
        _expected = get_expected_account_str(account)
        click.echo(_expected)

    expected = get_expected_account_str(keyfile_account)
    result = runner.invoke(cmd, ["--account", keyfile_account.alias])
    assert expected in result.output


def test_account_option_uses_single_account_as_default(runner, one_account):
    """
    When there is only 1 test account, that is the default
    when no option is given.
    """

    @click.command()
    @account_option()
    def cmd(account):
        _expected = get_expected_account_str(account)
        click.echo(_expected)

    expected = get_expected_account_str(one_account)
    result = runner.invoke(cmd, [])
    assert expected in result.output


def test_account_prompts_when_more_than_one_keyfile_account(
    runner, keyfile_account, second_keyfile_account
):
    @click.command()
    @account_option()
    def cmd(account):
        _expected = get_expected_account_str(account)
        click.echo(_expected)

    expected = get_expected_account_str(keyfile_account)

    # Requires user input.
    result = runner.invoke(cmd, [], input="0\n")

    assert expected in result.output


def test_account_option_can_use_test_account(runner, test_accounts):
    index = 7
    test_account = test_accounts[index]

    @click.command()
    @account_option()
    def cmd(account):
        _expected = get_expected_account_str(account)
        click.echo(_expected)

    expected = get_expected_account_str(test_account)
    result = runner.invoke(cmd, ["--account", f"TEST::{index}"])
    assert expected in result.output


@pytest.mark.parametrize("opt", (0, "foo"))
def test_prompt_choice(runner, opt):
    """
    This demonstrates how to use ``PromptChoice``,
    as it is a little confusing, requiring a callback.
    """

    def choice_callback(ctx, param, value):
        return param.type.get_user_selected_choice()

    choice = PromptChoice(["foo", "bar"])
    assert hasattr(choice, "name")
    choice = PromptChoice(["foo", "bar"], name="choice")
    assert choice.name == "choice"

    @click.command()
    @click.option(
        "--choice",
        type=choice,
        callback=choice_callback,
    )
    def cmd(choice):
        click.echo(f"__expected_{choice}")

    result = runner.invoke(cmd, [], input=f"{opt}\n")
    assert "Select one of the following:" in result.output
    assert "__expected_foo" in result.output


def test_verbosity_option(runner):
    @click.command()
    @verbosity_option()
    def cmd():
        click.echo(f"__expected_{logger.level}")

    result = runner.invoke(cmd, ["--verbosity", logger.level])
    assert f"__expected_{logger.level}" in result.output


def test_account_prompt_name():
    """
    It is very important for this class to have the `name` attribute,
    even though it is not used. That is because some click internals
    expect this property to exist, and we skip the super() constructor.
    """
    option = AccountAliasPromptChoice()
    assert option.name == "account"
    option = AccountAliasPromptChoice(name="account_z")
    assert option.name == "account_z"


def test_contract_file_paths_argument(runner):
    @click.command()
    @contract_file_paths_argument()
    def cmd(file_paths):
        pass

    result = runner.invoke(cmd, ["path0", "path1"])
    assert "Contract 'path0' not found" in result.output
