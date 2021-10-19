from pathlib import Path

import pytest
from web3.exceptions import ContractLogicError

from ape.exceptions import VirtualMachineError
from ape.utils import get_relative_path, get_tx_error_from_web3_value_error

_TEST_DIRECTORY_PATH = Path("/This/is/a/test/")
_TEST_FILE_PATH = _TEST_DIRECTORY_PATH / "scripts" / "script.py"
_TEST_REVERT_REASON = "TEST REVERT REASON"


def test_get_relative_path_from_project():
    actual = get_relative_path(_TEST_FILE_PATH, _TEST_DIRECTORY_PATH)
    expected = Path("scripts/script.py")
    assert actual == expected


def test_get_relative_path_given_relative_path():
    relative_script_path = Path("../deploy.py")
    with pytest.raises(ValueError) as err:
        get_relative_path(relative_script_path, _TEST_DIRECTORY_PATH)

    assert str(err.value) == "'target' must be an absolute path."

    relative_project_path = Path("../This/is/a/test")

    with pytest.raises(ValueError) as err:
        get_relative_path(_TEST_FILE_PATH, relative_project_path)

    assert str(err.value) == "'anchor' must be an absolute path."


def test_get_relative_path_same_path():
    actual = get_relative_path(_TEST_FILE_PATH, _TEST_FILE_PATH)
    assert actual == Path()


def test_get_relative_path_roots():
    root = Path("/")
    actual = get_relative_path(root, root)
    assert actual == Path()


@pytest.mark.parametrize(
    "error_dict",
    (
        {"message": "The transaction ran out of gas", "code": -32000},
        {"message": "Base limit exceeds gas limit", "code": -32603},
        {"message": "Exceeds block gas limit", "code": -32603},
        {"message": "Transaction requires at least 12345 gas"},
    ),
)
def test_get_tx_error_from_web3_value_error_gas_related(error_dict):
    error_dict[
        "message"
    ] = f"Error: VM Exception while processing transaction: {error_dict['message']}"
    test_err = ValueError(error_dict)
    actual = get_tx_error_from_web3_value_error(test_err)
    assert type(actual) != VirtualMachineError


def test_get_tx_error_from_web3_value_error_hardhat():
    err_data = {
        "message": (
            "Error: VM Exception while processing transaction: "
            f"reverted with reason string '{_TEST_REVERT_REASON}'"
        )
    }
    test_err = ValueError(err_data)
    actual = get_tx_error_from_web3_value_error(test_err)
    assert type(actual) == VirtualMachineError


def test_get_tx_error_from_web3_value_error_ganache():
    test_err = ContractLogicError(
        f"execution reverted: Transaction revert message: execution reverted: "
        f"VM Exception while processing transaction: revert {_TEST_REVERT_REASON}"
    )
    actual = get_tx_error_from_web3_value_error(test_err)
    assert isinstance(actual, VirtualMachineError)
    assert actual.revert_message == _TEST_REVERT_REASON
