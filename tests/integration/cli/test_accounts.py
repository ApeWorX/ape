import json
from pathlib import Path

import pytest
from eth_account import Account  # type: ignore

from tests.integration.cli.utils import assert_failure

ALIAS = "test"
PASSWORD = "a"
PRIVATE_KEY = "0000000000000000000000000000000000000000000000000000000000000001"
IMPORT_VALID_INPUT = "\n".join([f"0x{PRIVATE_KEY}", PASSWORD, PASSWORD])
GENERATE_VALID_INPUT = "\n".join(["random entropy", PASSWORD, PASSWORD])


@pytest.fixture
def keyparams():
    # NOTE: password is 'a'
    return {
        "address": "7e5f4552091a69125d5dfcb7b8c2659029395bdf",
        "crypto": {
            "cipher": "aes-128-ctr",
            "cipherparams": {"iv": "7bc492fb5dca4fe80fd47645b2aad0ff"},
            "ciphertext": "43beb65018a35c31494f642ec535315897634b021d7ec5bb8e0e2172387e2812",
            "kdf": "scrypt",
            "kdfparams": {
                "dklen": 32,
                "n": 262144,
                "r": 1,
                "p": 8,
                "salt": "4b127cb5ddbc0b3bd0cc0d2ef9a89bec",
            },
            "mac": "6a1d520975a031e11fc16cff610f5ae7476bcae4f2f598bc59ccffeae33b1caa",
        },
        "id": "ee424db9-da20-405d-bd75-e609d3e2b4ad",
        "version": 3,
    }


@pytest.fixture(autouse=True)
def temp_keyfile_path(config):
    temp_accounts_dir = Path(config.DATA_FOLDER) / "accounts"
    temp_accounts_dir.mkdir(exist_ok=True, parents=True)
    test_keyfile_path = temp_accounts_dir / f"{ALIAS}.json"

    if test_keyfile_path.exists():
        # Corrupted from a previous test
        test_keyfile_path.unlink()

    return test_keyfile_path


@pytest.fixture
def temp_keyfile(temp_keyfile_path, keyparams):
    temp_keyfile_path.write_text(json.dumps(keyparams))

    yield temp_keyfile_path

    if temp_keyfile_path.exists():
        temp_keyfile_path.unlink()


@pytest.fixture
def temp_account():
    return Account.from_key(bytes.fromhex(PRIVATE_KEY))


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
