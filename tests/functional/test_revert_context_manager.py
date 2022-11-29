import pytest

from ape.pytest.contextmanagers import RevertsContextManager as reverts
from tests.conftest import geth_process_test


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


@geth_process_test
def test_dev_revert(owner, reverts_contract_instance, geth_provider):
    """
    Test catching transaction reverts and asserting on a dev message written in the contract source
    code.
    """

    with reverts(dev_message="dev: error"):
        reverts_contract_instance.revertStrings(2, sender=owner)


@geth_process_test
def test_dev_revert_fails(owner, reverts_contract_instance, geth_provider):
    """
    Test that ``AssertionError`` is raised if the supplied dev message does not match the actual
    dev message found in the contract at the source of the revert.
    """

    with pytest.raises(AssertionError):
        with reverts(dev_message="dev: foo"):
            reverts_contract_instance.revertStrings(2, sender=owner)


@geth_process_test
def test_both(owner, reverts_contract_instance, geth_provider):
    """
    Test catching transaction reverts and asserting on the revert reason as well as a dev message
    written in the contract source code.
    """

    with reverts(expected_message="two", dev_message="dev: error"):
        reverts_contract_instance.revertStrings(2, sender=owner)
