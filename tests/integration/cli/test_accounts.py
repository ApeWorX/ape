import json

import pytest
from eth_account import Account
from eth_account.hdaccount import ETHEREUM_DEFAULT_PATH

from tests.integration.cli.utils import assert_failure, run_once

ALIAS = "test"
PASSWORD = "a"
PRIVATE_KEY = "0000000000000000000000000000000000000000000000000000000000000001"
MNEMONIC = "test test test test test test test test test test test junk"
INVALID_MNEMONIC = "test test"
CUSTOM_HDPATH = "m/44'/61'/0'/0/0"  # Ethereum Classic ($ETC) HDPath


@pytest.fixture(autouse=True)
def temp_keyfile_path(temp_accounts_path):
    test_keyfile_path = temp_accounts_path / f"{ALIAS}.json"

    if test_keyfile_path.is_file():
        # Corrupted from a previous test
        test_keyfile_path.unlink()

    return test_keyfile_path


@pytest.fixture
def temp_keyfile(temp_keyfile_path, keyparams):
    temp_keyfile_path.write_text(json.dumps(keyparams))

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
        ["accounts", "import", ALIAS],
        input="\n".join([f"0x{PRIVATE_KEY}", PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    assert temp_account.address in result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.is_file()


@run_once
def test_import_invalid_private_key(ape_cli, runner):
    # Add account from invalid private key
    result = runner.invoke(
        ape_cli,
        ["accounts", "import", ALIAS],
        input="\n".join(["0xhello", PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 1, result.output
    assert_failure(result, "Key can't be imported: Non-hexadecimal digit found")


@run_once
def test_import_alias_already_in_use(ape_cli, runner):
    def invoke_import():
        return runner.invoke(
            ape_cli,
            ["accounts", "import", ALIAS],
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
        ["accounts", "import", ALIAS],
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
        ["accounts", "import", "--use-mnemonic", ALIAS],
        input="\n".join([f"{MNEMONIC}", PASSWORD, PASSWORD]),
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
        ["accounts", "import", ALIAS, "--use-mnemonic", "--hd-path", CUSTOM_HDPATH],
        input="\n".join([f"{MNEMONIC}", PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    assert temp_account_mnemonic_custom_hdpath.address in result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.is_file()


@run_once
def test_export(ape_cli, runner, temp_keyfile):
    address = json.loads(temp_keyfile.read_text())["address"]
    # export key
    result = runner.invoke(
        ape_cli,
        ["accounts", "export", ALIAS],
        input="\n".join([PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    assert f"0x{PRIVATE_KEY}" in result.output
    assert address in result.output


@run_once
def test_import_invalid_mnemonic(ape_cli, runner):
    # Add account from invalid mnemonic
    result = runner.invoke(
        ape_cli,
        ["accounts", "import", "--use-mnemonic", ALIAS],
        input="\n".join([f"{INVALID_MNEMONIC}", PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 1, result.output
    assert_failure(
        result,
        f"Seed phrase can't be imported: Provided words: '{INVALID_MNEMONIC}'"
        + ", are not a valid BIP39 mnemonic phrase!",
    )


@run_once
def test_generate_default(ape_cli, runner, temp_keyfile_path):
    assert not temp_keyfile_path.is_file()
    # Generate new private key
    show_mnemonic = ""
    result = runner.invoke(
        ape_cli,
        ["accounts", "generate", ALIAS],
        input="\n".join(["random entropy", show_mnemonic, PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    assert "Newly generated mnemonic is" in result.output
    mnemonic_length = len(result.output.split(":")[4].split("\n")[0].split())
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
        ["accounts", "generate", ALIAS],
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
        ["accounts", "generate", ALIAS, "--hide-mnemonic"],
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
        ["accounts", "generate", ALIAS, "--word-count", word_count],
        input="\n".join(["random entropy", show_mnemonic, PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    assert "Newly generated mnemonic is" in result.output
    mnemonic_length = len(result.output.split(":")[4].split("\n")[0].split())
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
        ["accounts", "generate", ALIAS, "--hd-path", CUSTOM_HDPATH],
        input="\n".join(["random entropy", show_mnemonic, PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    assert "Newly generated mnemonic is" in result.output
    mnemonic_length = len(result.output.split(":")[4].split("\n")[0].split())
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
        ["accounts", "generate", ALIAS, "--word-count", word_count, "--hd-path", CUSTOM_HDPATH],
        input="\n".join(["random entropy", show_mnemonic, PASSWORD, PASSWORD]),
    )
    assert result.exit_code == 0, result.output
    assert "Newly generated mnemonic is" in result.output
    mnemonic_length = len(result.output.split(":")[4].split("\n")[0].split())
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
            ["accounts", "generate", ALIAS],
            input="\n".join(["random entropy", show_mnemonic, PASSWORD, PASSWORD]),
        )

    result = invoke_generate()
    assert result.exit_code == 0, result.output
    result = invoke_generate()
    assert_failure(result, f"Account with alias '{ALIAS}' already in use")


@run_once
def test_list(ape_cli, runner, temp_keyfile):
    # Check availability
    assert temp_keyfile.is_file()
    result = runner.invoke(ape_cli, ["accounts", "list"], catch_exceptions=False)
    assert ALIAS in result.output

    # NOTE: the un-checksummed version of this address is found in the temp_keyfile fixture.
    expected_address = "0x7E5F4552091A69125d5DfCb7b8C2659029395Bdf"
    assert expected_address in result.output


@run_once
def test_list_all(ape_cli, runner, temp_keyfile):
    # Check availability
    assert temp_keyfile.is_file()
    result = runner.invoke(ape_cli, ["accounts", "list", "--all"])
    assert ALIAS in result.output


@run_once
def test_change_password(ape_cli, runner, temp_keyfile):
    assert temp_keyfile.is_file()
    # Delete Account (`N` for "Leave unlocked?")
    valid_input = [PASSWORD, "N", "b", "b"]
    result = runner.invoke(
        ape_cli,
        ["accounts", "change-password", ALIAS],
        input="\n".join(valid_input) + "\n",
    )
    assert result.exit_code == 0, result.output


@run_once
def test_delete(ape_cli, runner, temp_keyfile):
    assert temp_keyfile.is_file()
    # Delete Account
    result = runner.invoke(ape_cli, ["accounts", "delete", ALIAS], input=f"{PASSWORD}\n")
    assert result.exit_code == 0, result.output
    assert not temp_keyfile.is_file()
