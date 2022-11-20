from typing import List
from unittest.mock import MagicMock

import pytest
from ethpm_types import ContractInstance
from evm_trace import TraceFrame

from ape.pytest.contextmanagers import RevertsContextManager as reverts


def make_mock_trace(contract: ContractInstance, expected_dev_message: str) -> List[TraceFrame]:
    """
    Create a mock REVERT frame whose PC location aligns with the line for the given
    ``expected_dev_message``.

    Only the ``TraceFrame.pc`` value will be used by RevertsContextManager.
    """
    pcmap = contract.contract_type.pcmap.parse()
    dev_messages = contract.contract_type.dev_messages

    expected_line = None
    for line, message in dev_messages.items():
        if message == expected_dev_message:
            expected_line = line
            break

    if expected_line is not None:
        for pc, line_info in pcmap.items():
            if line_info.line_start == expected_line:
                return [
                    TraceFrame(
                        pc=pc,
                        op="REVERT",
                        gas=0,
                        gasCost=0,
                        depth=0,
                        stack=[],
                        memory=[],
                    )
                ]

    raise AssertionError("")


@pytest.fixture(scope="function")
def mock_trace(mocker):
    """
    Allows tests to patch in a mock stack trace to facilitate RevertsContextManager testing.
    """
    return mocker.patch("ape.api.providers.ProviderAPI.get_transaction_trace", MagicMock())


def test_no_args(owner, reverts_contract_instance):
    """
    Test catching transaction reverts without asserting on error messages.
    """
    with reverts():
        reverts_contract_instance.revertStrings(0, sender=owner)


def test_revert_msg(owner, reverts_contract_instance):
    """
    Test catching transaction reverts and asserting on the revert reason.
    """
    with reverts("zero"):
        reverts_contract_instance.revertStrings(0, sender=owner)


def test_revert_msg_raises_incorrect(owner, reverts_contract_instance):
    """
    Test that ``AssertionError`` is raised if the supplied revert reason does not match the actual
    revert reason.
    """
    with pytest.raises(AssertionError):
        with reverts("one"):
            reverts_contract_instance.revertStrings(0, sender=owner)


def test_revert_msg_raises_partial(owner, reverts_contract_instance):
    """
    Test that ``AssertionError`` is raised if the supplied revert reason does not match the actual
    revert reason exactly.
    """
    with pytest.raises(AssertionError):
        with reverts("ze"):
            reverts_contract_instance.revertStrings(0, sender=owner)


def test_dev_revert(owner, reverts_contract_instance, mock_trace):
    """
    Test catching transaction reverts and asserting on a dev message written in the contract source
    code.
    """
    mock_trace.return_value = make_mock_trace(reverts_contract_instance, "dev: error")

    with reverts(dev_message="dev: error"):
        reverts_contract_instance.revertStrings(2, sender=owner)


def test_dev_revert_fails(owner, reverts_contract_instance, mock_trace):
    """
    Test that ``AssertionError`` is raised if the supplied dev message does not match the actual
    dev message found in the contract at the source of the revert.
    """
    mock_trace.return_value = make_mock_trace(reverts_contract_instance, "dev: error")

    with pytest.raises(AssertionError):
        with reverts(dev_message="dev: foo"):
            reverts_contract_instance.revertStrings(2, sender=owner)


def test_both(owner, reverts_contract_instance, mock_trace):
    """
    Test catching transaction reverts and asserting on the revert reason as well as a dev message
    written in the contract source code.
    """
    mock_trace.return_value = make_mock_trace(reverts_contract_instance, "dev: error")

    with reverts(expected_message="two", dev_message="dev: error"):
        reverts_contract_instance.revertStrings(2, sender=owner)
