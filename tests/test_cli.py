from pathlib import Path

import pytest  # type: ignore
from eth_account import Account  # type: ignore
from hypothesis import given, settings  # type: ignore
from hypothesis import strategies as st  # type: ignore

from ape import config


@pytest.mark.parametrize(
    "args",
    (
        [],
        ["--version"],
        ["--config"],
        ["--help"],
        ["accounts"],
        ["accounts", "list"],
        ["compile"],
        ["console"],
        ["console", "--verbose"],
        ["plugins"],
        ["plugins", "list"],
    ),
)
def test_invocation(ape_cli, runner, args):
    result = runner.invoke(ape_cli, args)
    assert result.exit_code == 0


word_st = st.text(alphabet=list("abcdefghijklmnopqrstuvwxyz"), min_size=3, max_size=7)


@pytest.mark.fuzzing
@given(
    alias=word_st,
    password=word_st,
    private_key=st.binary(min_size=32, max_size=32).map(lambda k: k.hex()),
)
@settings(deadline=1000)
def test_keygen(ape_cli, runner, alias, password, private_key):
    keyfile = Path(config.DATA_FOLDER / "accounts" / f"{alias}.json")
    if keyfile.exists():
        keyfile.unlink()

    valid_input = ["0x" + private_key, password, password]
    result = runner.invoke(ape_cli, ["accounts", "import", alias], input="\n".join(valid_input))
    assert result.exit_code == 0
    assert Account.from_key(bytes.fromhex(private_key)).address in result.output
    assert alias in result.output

    if keyfile.exists():
        keyfile.unlink()
