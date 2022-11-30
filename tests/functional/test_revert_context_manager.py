import re

import pytest

from ape.pytest.contextmanagers import RevertsContextManager as reverts
from tests.conftest import geth_process_test


def test_no_args(owner, reverts_contract_instance):
    """
    Test catching transaction reverts without asserting on error messages.
    """
    with reverts():
        reverts_contract_instance.revertStrings(0, sender=owner)


def test_revert(owner, reverts_contract_instance):
    """
    Test matching a revert message with a supplied message.
    """
    with reverts("zero"):
        reverts_contract_instance.revertStrings(0, sender=owner)


def test_revert_pattern(owner, reverts_contract_instance):
    """
    Test matching a revert message with a supplied pattern.
    """
    with reverts(re.compile(r"ze\w+")):
        reverts_contract_instance.revertStrings(0, sender=owner)


def test_revert_fails(owner, reverts_contract_instance):
    """
    Test that ``AssertionError`` is raised if the supplied revert reason does not match the actual
    revert reason.
    """
    with pytest.raises(AssertionError):
        with reverts("one"):
            reverts_contract_instance.revertStrings(0, sender=owner)


def test_revert_pattern_fails(owner, reverts_contract_instance):
    """
    Test that ``AssertionError`` is raised if the actual revert reason does not match the supplied
    revert pattern.
    """
    with pytest.raises(AssertionError):
        with reverts(re.compile(r"[^zero]+")):
            reverts_contract_instance.revertStrings(0, sender=owner)


def test_revert_partial_fails(owner, reverts_contract_instance):
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
    Test matching a contract dev revert message with a supplied dev message.
    """
    with reverts(dev_message="dev: error"):
        reverts_contract_instance.revertStrings(2, sender=owner)


@geth_process_test
def test_dev_revert_pattern(owner, reverts_contract_instance, geth_provider):
    """
    Test matching a contract dev revert message with a supplied dev message pattern.
    """
    with reverts(dev_message=re.compile(r"dev: err\w+")):
        reverts_contract_instance.revertStrings(2, sender=owner)


@geth_process_test
def test_dev_revert_fails(owner, reverts_contract_instance, geth_provider):
    """
    Test that ``AssertionError`` is raised if the supplied dev message and the contract dev message
    do not match.
    """
    with pytest.raises(AssertionError):
        with reverts(dev_message="dev: foo"):
            reverts_contract_instance.revertStrings(2, sender=owner)


@geth_process_test
def test_dev_revert_partial_fails(owner, reverts_contract_instance, geth_provider):
    """
    Test that ``AssertionError`` is raised if the supplied dev message and the contract dev message
    do not match exactly.
    """
    with pytest.raises(AssertionError):
        with reverts(dev_message="dev: foo"):
            reverts_contract_instance.revertStrings(2, sender=owner)


@geth_process_test
def test_dev_revert_pattern_fails(owner, reverts_contract_instance, geth_provider):
    """
    Test that ``AssertionError`` is raised if the contract dev message does not match the supplied
    dev revert pattern.
    """
    with pytest.raises(AssertionError):
        with reverts(dev_message=re.compile(r"dev: [^ero]+")):
            reverts_contract_instance.revertStrings(2, sender=owner)


@geth_process_test
def test_both_message_and_dev_str(owner, reverts_contract_instance, geth_provider):
    """
    Test matching a revert message with a supplied message as well as a contract dev revert message
    with a supplied dev message.
    """
    with reverts(expected_message="two", dev_message="dev: error"):
        reverts_contract_instance.revertStrings(2, sender=owner)
