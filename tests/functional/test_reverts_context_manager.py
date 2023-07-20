import re

import pytest

from ape.pytest.contextmanagers import RevertsContextManager as reverts
from tests.conftest import geth_process_test


def test_revert_info_context(owner, reverts_contract_instance):
    """
    Shows no two revert info objects are the same instance.
    """

    rev = reverts()
    with rev as rev0:
        reverts_contract_instance.revertStrings(0, sender=owner)
    with rev as rev1:
        reverts_contract_instance.revertStrings(1, sender=owner)

    assert rev0.value.revert_message != rev1.value.revert_message


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


def test_revert_error(error_contract, not_owner):
    """
    Test matching a revert custom Solidity error.
    """
    with reverts(error_contract.Unauthorized):
        error_contract.withdraw(sender=not_owner)


def test_revert_abi(error_contract, not_owner):
    """
    Test matching a revert custom Solidity error using an ABI.
    """
    with reverts(error_contract.Unauthorized.abi):
        error_contract.withdraw(sender=not_owner)


def test_revert_error_from_container(error_contract_container, error_contract, not_owner):
    """
    Test matching a revert custom Solidity error using the container instead
    of an instance, so the specific contract instance is not checked, only the
    ABI is. This is required for proper deploy-txn checks.
    """
    with reverts(error_contract_container.Unauthorized):
        error_contract.withdraw(sender=not_owner)


def test_revert_error_from_container_with_expected_values(
    error_contract_container, error_contract, not_owner
):
    """
    Test matching a revert custom Solidity error using the container instead
    of an instance, so the specific contract instance is not checked, only the
    ABI is. This is required for proper deploy-txn checks.
    """
    with reverts(error_contract_container.Unauthorized, error_inputs={"addr": not_owner.address}):
        error_contract.withdraw(sender=not_owner)


def test_revert_unexpected_error(error_contract, not_owner):
    """
    Test when given a different error type than what was raised.
    """
    expected = "Expected error 'OtherError' but was 'Unauthorized'"
    with pytest.raises(AssertionError, match=expected):
        with reverts(error_contract.OtherError):
            error_contract.withdraw(sender=not_owner)


def test_revert_error_inputs(error_contract, not_owner):
    """
    Test matching a revert custom Solidity error with inputs.
    """
    with reverts(error_contract.Unauthorized, addr=not_owner.address, counter=123):
        error_contract.withdraw(sender=not_owner)


def test_revert_error_unexpected_inputs(error_contract, owner, not_owner):
    """
    Test matching a revert custom Solidity error with unexpected inputs.
    """
    expected = (
        rf"Expected input 'addr' to be '{owner.address}' but was '{not_owner.address}'\."
        r"\nExpected input 'counter' to be '321' but was '123'\."
    )
    with pytest.raises(AssertionError, match=expected):
        with reverts(error_contract.Unauthorized, addr=owner.address, counter=321):
            error_contract.withdraw(sender=not_owner)


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

    # Show a method further down in the contract also works.
    with reverts(dev_message="dev: error"):
        reverts_contract_instance.revertStrings2(2, sender=owner)


@geth_process_test
def test_dev_revert_pattern(owner, reverts_contract_instance, geth_provider):
    """
    Test matching a contract dev revert message with a supplied dev message pattern.
    """
    with reverts(dev_message=re.compile(r"dev: err\w+")):
        reverts_contract_instance.revertStrings(2, sender=owner)

    with reverts(dev_message=re.compile(r"dev: err\w+")):
        reverts_contract_instance.revertStrings2(2, sender=owner)


@geth_process_test
def test_dev_revert_from_sub_contract(owner, reverts_contract_instance, geth_provider):
    """
    Test to ensure we can assert on dev messages from inner-contracts.
    """
    with reverts(dev_message="dev: sub-zero"):
        reverts_contract_instance.subRevertStrings(0, sender=owner)


@geth_process_test
def test_dev_revert_deep_in_method(owner, reverts_contract_instance, geth_provider):
    """
    Test to ensure we can assert on a dev message that is in the middle of a
    complicated function implementation.
    """
    with reverts(dev_message="dev: foobarbaz"):
        reverts_contract_instance.revertStrings(13, sender=owner)

    with reverts(dev_message="dev: such modifiable, wow"):
        reverts_contract_instance.revertStrings(4, sender=owner)

    with reverts(dev_message="dev: great job"):
        reverts_contract_instance.revertStrings(31337, sender=owner)


def test_dev_revert_in_loop(owner, reverts_contract_instance, geth_provider):
    with reverts(dev_message="dev: loop test"):
        reverts_contract_instance.revertStrings2(12, sender=owner)


@geth_process_test
def test_dev_revert_nonpayable_check(owner, vyper_contract_container, geth_provider):
    """
    Tests that we can assert on dev messages injected from the compiler.
    """
    contract = owner.deploy(vyper_contract_container, 0)
    with reverts(dev_message="dev: Cannot send ether to non-payable function"):
        contract.setNumber(123, sender=owner, value=1)


@geth_process_test
def test_dev_revert_math_dev_checks(owner, vyper_math_dev_check, geth_provider):
    """
    Tests that we can assert on dev messages injected from the compiler.
    """
    contract = owner.deploy(vyper_math_dev_check)

    with reverts(dev_message="dev: Integer overflow"):
        contract.num_add(1, sender=owner)

    with reverts(dev_message="dev: Integer underflow"):
        contract.neg_num_add(-2, sender=owner)

    with reverts(dev_message="dev: Division by zero"):
        contract.div_zero(0, sender=owner)

    with reverts(dev_message="dev: Modulo by zero"):
        contract.mod_zero(0, sender=owner)


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
def test_dev_revert_on_call(owner, reverts_contract_instance, geth_provider):
    """
    Shows that dev strings are detectable even on pure / view methods.
    """
    with reverts(dev_message="dev: one"):
        reverts_contract_instance.revertStringsCall(1)


@geth_process_test
def test_both_message_and_dev_str(owner, reverts_contract_instance, geth_provider):
    """
    Test matching a revert message with a supplied message as well as a contract dev revert message
    with a supplied dev message.
    """
    with reverts(expected_message="two", dev_message="dev: error"):
        reverts_contract_instance.revertStrings(2, sender=owner)
