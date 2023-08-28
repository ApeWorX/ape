import re

import pytest

from ape.pytest.contextmanagers import RevertsContextManager as reverts


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
