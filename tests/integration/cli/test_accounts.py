import json
import re
from typing import Optional

import pytest
from eth_account import Account
from eth_account.hdaccount import ETHEREUM_DEFAULT_PATH

from ape.logging import HIDDEN_MESSAGE
from tests.integration.cli.utils import assert_failure, run_once

ALIAS = "test"
PASSWORD = "asdf1234"
PRIVATE_KEY = "0000000000000000000000000000000000000000000000000000000000000001"
MNEMONIC = "test test test test test test test test test test test junk"
INVALID_MNEMONIC = "test test"
CUSTOM_HDPATH = "m/44'/61'/0'/0/0"  # Ethereum Classic ($ETC) HDPath


def extract_mnemonic(output: str) -> Optional[list[str]]:
    found = re.search(r"Newly generated mnemonic is: ([a-z ]+)", output)
    if found:
        try:
            mnemonic_string = found.group(1)
            return mnemonic_string.split(" ")
        except IndexError:
            pass
    return None


@pytest.fixture(autouse=True)
def temp_keyfile_path(config):
    # NOTE: Is a fresh account for each use.
    path = config.DATA_FOLDER / "accounts" / f"{ALIAS}.json"
    path.parent.mkdir(parents=True, exist_ok=True)  # create accounts subfolder
    path.unlink(missing_ok=True)
    return path


@pytest.fixture
def temp_keyfile(temp_keyfile_path, keyparams):
    temp_keyfile_path.write_text(json.dumps(keyparams), encoding="utf8")

    yield temp_keyfile_path

    if temp_keyfile_path.is_file():
        temp_keyfile_path.unlink()


@pytest.fixture
def temp_account():
    return Account.from_key(bytes.fromhex(PRIVATE_KEY))


@pytest.fixture()
def temp_account_mnemonic_default_hdpath():
    Account.enable_unaudited_hdwallet_features()
    return Account.from_mnemonic(MNEMONIC, account_path=ETHEREUM_DEFAULT_PATH)


@pytest.fixture()
def temp_account_mnemonic_custom_hdpath():
    Account.enable_unaudited_hdwallet_features()
    return Account.from_mnemonic(MNEMONIC, account_path=CUSTOM_HDPATH)


@run_once
def test_import_valid_private_key(ape_cli, runner, temp_account, temp_keyfile_path):
    assert not temp_keyfile_path.is_file()
    # Add account from valid private key
    result = runner.invoke(
        ape_cli,
        ("accounts", "import", ALIAS),
        input="\n".join([f"0x{PRIVATE_KEY}", PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    assert temp_account.address in result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.is_file()


@run_once
def test_import_alias_is_private_key(ape_cli, runner):
    # Attempt using private key as the alias.
    key_alias = f"0x{PRIVATE_KEY}"
    result = runner.invoke(
        ape_cli,
        ("accounts", "import", key_alias),
        input="\n".join([f"0x{PRIVATE_KEY}", PASSWORD, PASSWORD]),
    )
    assert result.exit_code != 0, result.output
    assert "ERROR" in result.output
    expected = "(AccountsError) Longer aliases cannot be hex strings.\n"
    assert expected in result.output


@run_once
def test_import_alias_is_really_long(ape_cli, runner):
    """
    For entropy related use-cases regarding alias, we
    must ensure long aliases are supported.
    """

    long_alias = "this is a long alias that i am going to use and you can't stop me"
    result = runner.invoke(
        ape_cli,
        ("accounts", "import", long_alias),
        input="\n".join([f"0x{PRIVATE_KEY}", PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0


@run_once
def test_import_invalid_private_key(ape_cli, runner):
    # Add account from invalid private key
    result = runner.invoke(
        ape_cli,
        ("accounts", "import", ALIAS),
        input="\n".join(["0xhello", PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 1, result.output
    assert_failure(result, "Key can't be imported: Non-hexadecimal digit found")


@run_once
def test_import_alias_already_in_use(ape_cli, runner):
    def invoke_import():
        return runner.invoke(
            ape_cli,
            ("accounts", "import", ALIAS),
            input="\n".join([f"0x{PRIVATE_KEY}", PASSWORD, PASSWORD]),
        )

    result = invoke_import()
    assert result.exit_code == 0, result.output
    result = invoke_import()
    assert_failure(result, f"Account with alias '{ALIAS}' already in use")


@run_once
def test_import_account_instantiation_failure(mocker, ape_cli, runner):
    eth_account_from_key_patch = mocker.patch("ape_accounts._cli.EthAccount.from_key")
    eth_account_from_key_patch.side_effect = Exception("Can't instantiate this account!")
    result = runner.invoke(
        ape_cli,
        ("accounts", "import", ALIAS),
        input="\n".join([f"0x{PRIVATE_KEY}", PASSWORD, PASSWORD]),
    )
    assert_failure(result, "Key can't be imported: Can't instantiate this account!")


@run_once
def test_import_mnemonic_default_hdpath(
    ape_cli, runner, temp_account_mnemonic_default_hdpath, temp_keyfile_path
):
    assert not temp_keyfile_path.is_file()
    # Add account from mnemonic with default hdpath of ETHEREUM_DEFAULT_PATH
    result = runner.invoke(
        ape_cli,
        ("accounts", "import", "--use-mnemonic", ALIAS),
        input="\n".join([MNEMONIC, PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    assert temp_account_mnemonic_default_hdpath.address in result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.is_file()


@run_once
def test_import_mnemonic_custom_hdpath(
    ape_cli, runner, temp_account_mnemonic_custom_hdpath, temp_keyfile_path
):
    assert not temp_keyfile_path.is_file()
    # Add account from mnemonic with custom hdpath
    result = runner.invoke(
        ape_cli,
        ("accounts", "import", ALIAS, "--use-mnemonic", "--hd-path", CUSTOM_HDPATH),
        input="\n".join([MNEMONIC, PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    assert temp_account_mnemonic_custom_hdpath.address in result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.is_file()


@run_once
def test_export(ape_cli, runner, temp_keyfile, keyfile_account, accounts):
    # export key
    result = runner.invoke(
        ape_cli,
        ("accounts", "export", ALIAS),
        input="\n".join([PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    # NOTE: temp_keyfile uses the same address as the keyfile account.
    assert keyfile_account.address in result.output
    # NOTE: Both of these accounts are the same as the first
    #   test account.
    assert accounts[0].private_key in result.output


@run_once
def test_import_invalid_mnemonic(ape_cli, runner):
    # Add account from invalid mnemonic
    result = runner.invoke(
        ape_cli,
        ("accounts", "import", "--use-mnemonic", ALIAS),
        input="\n".join([INVALID_MNEMONIC, PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 1, result.output
    assert_failure(result, "Seed phrase can't be imported")
    assert HIDDEN_MESSAGE in result.output
    assert INVALID_MNEMONIC not in result.output


@run_once
def test_generate_default(ape_cli, runner, temp_keyfile_path):
    assert not temp_keyfile_path.is_file()
    # Generate new private key
    show_mnemonic = ""
    result = runner.invoke(
        ape_cli,
        ("accounts", "generate", ALIAS),
        input="\n".join(["random entropy", show_mnemonic, PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    mnemonic = extract_mnemonic(result.output)
    assert mnemonic is not None
    mnemonic_length = len(mnemonic)
    assert mnemonic_length == 12
    assert ETHEREUM_DEFAULT_PATH in result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.is_file()


@run_once
def test_generate_hide_mnemonic_prompt(ape_cli, runner, temp_keyfile_path):
    assert not temp_keyfile_path.is_file()
    # Generate new private key
    show_mnemonic = "n"
    result = runner.invoke(
        ape_cli,
        ("accounts", "generate", ALIAS),
        input="\n".join(["random entropy", show_mnemonic, PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    assert "Newly generated mnemonic is" not in result.output
    assert ETHEREUM_DEFAULT_PATH in result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.is_file()


@run_once
def test_generate_hide_mnemonic_option(ape_cli, runner, temp_keyfile_path):
    assert not temp_keyfile_path.is_file()
    # Generate new private key
    result = runner.invoke(
        ape_cli,
        ("accounts", "generate", ALIAS, "--hide-mnemonic"),
        input="\n".join(["random entropy", PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    assert "Newly generated mnemonic is" not in result.output
    assert ETHEREUM_DEFAULT_PATH in result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.is_file()


@run_once
def test_generate_24_words(ape_cli, runner, temp_keyfile_path):
    assert not temp_keyfile_path.is_file()
    # Generate new private key
    show_mnemonic = ""
    word_count = 24
    result = runner.invoke(
        ape_cli,
        ("accounts", "generate", ALIAS, "--word-count", word_count),
        input="\n".join(["random entropy", show_mnemonic, PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    mnemonic = extract_mnemonic(result.output)
    assert mnemonic is not None
    mnemonic_length = len(mnemonic)
    assert mnemonic_length == word_count
    assert ETHEREUM_DEFAULT_PATH in result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.is_file()


@run_once
def test_generate_custom_hdpath(ape_cli, runner, temp_keyfile_path):
    assert not temp_keyfile_path.is_file()
    # Generate new private key
    show_mnemonic = ""
    result = runner.invoke(
        ape_cli,
        ("accounts", "generate", ALIAS, "--hd-path", CUSTOM_HDPATH),
        input="\n".join(["random entropy", show_mnemonic, PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    mnemonic = extract_mnemonic(result.output)
    assert mnemonic is not None
    mnemonic_length = len(mnemonic)
    assert mnemonic_length == 12
    assert CUSTOM_HDPATH in result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.is_file()


@run_once
def test_generate_24_words_and_custom_hdpath(ape_cli, runner, temp_keyfile_path):
    assert not temp_keyfile_path.is_file()
    # Generate new private key
    show_mnemonic = ""
    word_count = 24
    result = runner.invoke(
        ape_cli,
        ("accounts", "generate", ALIAS, "--word-count", word_count, "--hd-path", CUSTOM_HDPATH),
        input="\n".join(["random entropy", show_mnemonic, PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    mnemonic = extract_mnemonic(result.output)
    assert mnemonic is not None
    mnemonic_length = len(mnemonic)
    assert mnemonic_length == word_count
    assert CUSTOM_HDPATH in result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.is_file()


@run_once
def test_generate_alias_already_in_use(ape_cli, runner):
    def invoke_generate():
        show_mnemonic = ""
        return runner.invoke(
            ape_cli,
            ("accounts", "generate", ALIAS),
            input="\n".join(["random entropy", show_mnemonic, PASSWORD, PASSWORD]),
        )

    result = invoke_generate()
    assert result.exit_code == 0, result.output
    result = invoke_generate()
    assert_failure(result, f"Account with alias '{ALIAS}' already in use")


@run_once
def test_list(ape_cli, runner, keyfile_account):
    result = runner.invoke(ape_cli, ("accounts", "list"), catch_exceptions=False)
    assert keyfile_account.alias in result.output
    assert keyfile_account.address in result.output


@run_once
def test_list_all(ape_cli, runner, keyfile_account):
    result = runner.invoke(ape_cli, ("accounts", "list", "--all"), catch_exceptions=False)
    assert keyfile_account.alias in result.output
    assert keyfile_account.address in result.output


@run_once
def test_change_password(ape_cli, runner, temp_keyfile):
    assert temp_keyfile.is_file()
    # Delete Account (`N` for "Leave unlocked?")
    valid_input = [PASSWORD, "N", "password2", "password2"]
    result = runner.invoke(
        ape_cli,
        ("accounts", "change-password", ALIAS),
        input="\n".join(valid_input) + "\n",
    )
    assert result.exit_code == 0, result.output


@run_once
def test_delete(ape_cli, runner, temp_keyfile):
    assert temp_keyfile.is_file()
    # Delete Account
    result = runner.invoke(ape_cli, ("accounts", "delete", ALIAS), input=f"{PASSWORD}\n")
    assert result.exit_code == 0, result.output
    assert not temp_keyfile.is_file()
