from tests.conftest import ALIAS, PRIVATE_KEY
from tests.integration.cli.utils import assert_failure

PASSWORD = "a"
IMPORT_VALID_INPUT = "\n".join([f"0x{PRIVATE_KEY}", PASSWORD, PASSWORD])
GENERATE_VALID_INPUT = "\n".join(["random entropy", PASSWORD, PASSWORD])


def test_import(ape_cli, runner, temp_account, temp_keyfile_path):
    assert not temp_keyfile_path.exists()
    # Add account from private keys
    result = runner.invoke(ape_cli, ["accounts", "import", ALIAS], input=IMPORT_VALID_INPUT)
    assert result.exit_code == 0, result.output
    assert temp_account.address in result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.exists()


def test_import_alias_already_in_use(ape_cli, runner, temp_account, temp_keyfile_path):
    def invoke_import():
        return runner.invoke(ape_cli, ["accounts", "import", ALIAS], input=IMPORT_VALID_INPUT)

    result = invoke_import()
    assert result.exit_code == 0, result.output
    result = invoke_import()
    assert_failure(result, f"Account with alias '{ALIAS}' already in use")


def test_import_account_instantiation_failure(
    mocker, ape_cli, runner, temp_account, temp_keyfile_path
):
    eth_account_from_key_patch = mocker.patch("ape_accounts._cli.EthAccount.from_key")
    eth_account_from_key_patch.side_effect = Exception("Can't instantiate this account!")
    result = runner.invoke(ape_cli, ["accounts", "import", ALIAS], input=IMPORT_VALID_INPUT)
    assert_failure(result, "Key can't be imported: Can't instantiate this account!")


def test_generate(ape_cli, runner, temp_keyfile_path):
    assert not temp_keyfile_path.exists()
    # Generate new private key
    result = runner.invoke(ape_cli, ["accounts", "generate", ALIAS], input=GENERATE_VALID_INPUT)
    assert result.exit_code == 0, result.output
    assert ALIAS in result.output
    assert temp_keyfile_path.exists()


def test_generate_alias_already_in_use(ape_cli, runner, temp_account, temp_keyfile_path):
    def invoke_generate():
        return runner.invoke(ape_cli, ["accounts", "generate", ALIAS], input=GENERATE_VALID_INPUT)

    result = invoke_generate()
    assert result.exit_code == 0, result.output
    result = invoke_generate()
    assert_failure(result, f"Account with alias '{ALIAS}' already in use")


def test_list(ape_cli, runner, temp_keyfile):
    # Check availability
    assert temp_keyfile.exists()
    result = runner.invoke(ape_cli, ["accounts", "list"])
    assert ALIAS in result.output


def test_list_all(ape_cli, runner, temp_keyfile):
    # Check availability
    assert temp_keyfile.exists()
    result = runner.invoke(ape_cli, ["accounts", "list", "--all"])
    assert ALIAS in result.output


def test_change_password(ape_cli, runner, temp_keyfile):
    assert temp_keyfile.exists()
    # Delete Account (`N` for "Leave unlocked?")
    valid_input = [PASSWORD, "N", "b", "b"]
    result = runner.invoke(
        ape_cli,
        ["accounts", "change-password", ALIAS],
        input="\n".join(valid_input) + "\n",
    )
    assert result.exit_code == 0, result.output


def test_delete(ape_cli, runner, temp_keyfile):
    assert temp_keyfile.exists()
    # Delete Account
    result = runner.invoke(ape_cli, ["accounts", "delete", ALIAS], input=PASSWORD + "\n")
    assert result.exit_code == 0, result.output
    assert not temp_keyfile.exists()
