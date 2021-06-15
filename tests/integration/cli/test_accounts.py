import json
from pathlib import Path

import pytest  # type: ignore
from eth_account import Account  # type: ignore

ALIAS = "test"
PASSWORD = "a"
PRIVATE_KEY = "0000000000000000000000000000000000000000000000000000000000000001"


@pytest.fixture
def test_keyparams():
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


@pytest.fixture
def test_keyfile_path(config):
    test_keyfile_path = Path(config.DATA_FOLDER / "accounts" / f"{ALIAS}.json")

    if test_keyfile_path.exists():
        # Corrupted from a previous test
        test_keyfile_path.unlink()

    return test_keyfile_path


@pytest.fixture
def test_keyfile(test_keyfile_path, test_keyparams):
    test_keyfile_path.write_text(json.dumps(test_keyparams))

    yield test_keyfile_path

    if test_keyfile_path.exists():
        test_keyfile_path.unlink()


@pytest.fixture
def test_account():
    return Account.from_key(bytes.fromhex(PRIVATE_KEY))


def test_import(ape_cli, runner, test_account, test_keyfile_path):
    assert not test_keyfile_path.exists()
    # Add account from private key
    valid_input = ["0x" + PRIVATE_KEY, PASSWORD, PASSWORD]
    result = runner.invoke(ape_cli, ["accounts", "import", ALIAS], input="\n".join(valid_input))
    assert result.exit_code == 0
    assert test_account.address in result.output
    assert ALIAS in result.output
    assert test_keyfile_path.exists()


def test_generate(ape_cli, runner, test_keyfile_path):
    assert not test_keyfile_path.exists()
    # Generate new private key
    valid_input = ["random entropy", PASSWORD, PASSWORD]
    result = runner.invoke(ape_cli, ["accounts", "generate", ALIAS], input="\n".join(valid_input))
    assert result.exit_code == 0
    assert ALIAS in result.output
    assert test_keyfile_path.exists()


def test_list(ape_cli, runner, test_keyfile):
    # Check availability
    assert test_keyfile.exists()
    result = runner.invoke(ape_cli, ["accounts", "list"])
    assert ALIAS in result.output


def test_change_password(ape_cli, runner, test_keyfile):
    assert test_keyfile.exists()
    # Delete Account (`N` for "Leave unlocked?")
    valid_input = [PASSWORD, "N", "b", "b"]
    result = runner.invoke(
        ape_cli, ["accounts", "change-password", ALIAS], input="\n".join(valid_input) + "\n"
    )
    assert result.exit_code == 0


def test_delete(ape_cli, runner, test_keyfile):
    assert test_keyfile.exists()
    # Delete Account
    result = runner.invoke(ape_cli, ["accounts", "delete", ALIAS], input=PASSWORD + "\n")
    assert result.exit_code == 0
    assert not test_keyfile.exists()
