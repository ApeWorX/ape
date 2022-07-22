import pytest

from ape.cli import get_user_selected_account
from ape.exceptions import AccountsError


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
    # No input needed when only one account
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
