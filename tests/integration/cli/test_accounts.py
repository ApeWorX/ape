from pathlib import Path

import pytest  # type: ignore
from eth_account import Account  # type: ignore

from ape import config


@pytest.mark.parametrize(
    "alias,password,private_key",
    [
        ("aaa", "a", "0000000000000000000000000000000000000000000000000000000000000001"),
    ],
)
def test_keygen(ape_cli, runner, alias, password, private_key):
    keyfile = Path(config.DATA_FOLDER / "accounts" / f"{alias}.json")
    if keyfile.exists():
        # Corrupted from a previous test
        keyfile.unlink()

    # Add account from private key
    valid_input = ["0x" + private_key, password, password]
    result = runner.invoke(ape_cli, ["accounts", "import", alias], input="\n".join(valid_input))
    assert result.exit_code == 0
    assert Account.from_key(bytes.fromhex(private_key)).address in result.output
    assert alias in result.output

    # Check availability
    result = runner.invoke(ape_cli, ["accounts", "list"])
    assert alias in result.output

    # Delete Account
    result = runner.invoke(ape_cli, ["accounts", "delete", alias], input=password + "\n")
    assert result.exit_code == 0
    assert not keyfile.exists()
