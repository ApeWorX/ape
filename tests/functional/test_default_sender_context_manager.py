import pytest

from ape.exceptions import SignatureError
from ape.pytest.contextmanagers import RevertsContextManager as reverts


def test_default_sender_test_account(solidity_contract_instance, owner, test_accounts):
    with test_accounts.use_sender(owner):
        tx = solidity_contract_instance.setNumber(1)
        assert tx.transaction.sender == owner.address
    with pytest.raises(SignatureError):
        solidity_contract_instance.setNumber(2)

    with test_accounts.use_sender(owner.address):
        tx = solidity_contract_instance.setNumber(1)
        assert tx.transaction.sender == owner.address

    with test_accounts.use_sender(owner.index):
        tx = solidity_contract_instance.setNumber(1)
        assert tx.transaction.sender == owner.address


def test_default_sender_account(
    solidity_contract_container, networks_connected_to_tester, accounts, keyfile_account
):
    owner = accounts[0]
    passphrase = "a"

    with accounts.use_sender(owner) as acct:
        acct.set_autosign(True, passphrase)
        contract = owner.deploy(solidity_contract_container, 0)

    with accounts.use_sender(owner) as acct:
        acct.set_autosign(True, passphrase)
        tx = contract.setNumber(1)
        assert tx.transaction.sender == owner.address

    with pytest.raises(SignatureError):
        contract.setNumber(2)

    with accounts.use_sender(owner.address) as acct:
        acct.set_autosign(True, passphrase)
        tx = contract.setNumber(1)
        assert tx.transaction.sender == owner.address

    with accounts.use_sender(owner.alias) as acct:
        acct.set_autosign(True, passphrase)
        tx = contract.setNumber(1)
        assert tx.transaction.sender == owner.address

    with accounts.use_sender(0) as acct:
        acct.set_autosign(True, passphrase)
        tx = contract.setNumber(1)
        assert tx.transaction.sender == owner.address


def test_nested_default_sender(solidity_contract_instance, owner, test_accounts):
    with test_accounts.use_sender(owner):
        tx = solidity_contract_instance.setNumber(1)
        assert tx.transaction.sender == owner.address
        with test_accounts.use_sender(test_accounts[0]):
            with reverts():
                solidity_contract_instance.setNumber(2)
        solidity_contract_instance.setNumber(3)
        assert tx.transaction.sender == owner.address


def test_with_error(solidity_contract_instance, accounts):
    # safe to use reverts with use_sender and when outside of the use_sender
    # there is no remaining default_user set
    user = accounts.test_accounts[0]
    with reverts("!authorized"):
        with accounts.test_accounts.use_sender(user):
            solidity_contract_instance.setNumber(2)
    assert accounts.default_sender is None
