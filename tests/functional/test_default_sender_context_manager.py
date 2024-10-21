import pytest

from ape.exceptions import SignatureError
from ape.pytest.contextmanagers import RevertsContextManager as reverts


def test_default_sender_test_account(solidity_contract_instance, owner, accounts):
    with accounts.use_sender(owner):
        tx = solidity_contract_instance.setNumber(1)
        assert tx.transaction.sender == owner.address
    with pytest.raises(SignatureError):
        solidity_contract_instance.setNumber(2)

    with accounts.use_sender(owner.address):
        tx = solidity_contract_instance.setNumber(1)
        assert tx.transaction.sender == owner.address

    with accounts.use_sender(owner.index):
        tx = solidity_contract_instance.setNumber(1)
        assert tx.transaction.sender == owner.address


def test_default_sender_account(
    solidity_contract_container,
    networks_connected_to_tester,
    account_manager,
    keyfile_account,
):
    passphrase = "asdf1234"

    with account_manager.use_sender(keyfile_account) as acct:
        acct.set_autosign(True, passphrase)
        contract = keyfile_account.deploy(solidity_contract_container, 0)

    with account_manager.use_sender(keyfile_account) as acct:
        acct.set_autosign(True, passphrase)
        tx = contract.setNumber(1)
        assert tx.transaction.sender == keyfile_account.address

    with pytest.raises(SignatureError):
        contract.setNumber(2)

    with account_manager.use_sender(keyfile_account.address) as acct:
        acct.set_autosign(True, passphrase)
        tx = contract.setNumber(1)
        assert tx.transaction.sender == keyfile_account.address

    with account_manager.use_sender(keyfile_account.alias) as acct:
        acct.set_autosign(True, passphrase)
        tx = contract.setNumber(1)
        assert tx.transaction.sender == keyfile_account.address

    with account_manager.use_sender(0) as acct:
        acct.set_autosign(True, passphrase)
        tx = contract.setNumber(1)
        assert tx.transaction.sender == keyfile_account.address


def test_nested_default_sender(solidity_contract_instance, owner, accounts, not_owner):
    with accounts.use_sender(owner):
        tx = solidity_contract_instance.setNumber(1)
        assert tx.transaction.sender == owner.address
        with accounts.use_sender(not_owner):
            with reverts():
                solidity_contract_instance.setNumber(2)

        solidity_contract_instance.setNumber(3)
        assert tx.transaction.sender == owner.address


def test_with_error(solidity_contract_instance, account_manager, not_owner):
    # safe to use reverts with use_sender and when outside of the use_sender
    # there is no remaining default_user set
    with reverts("!authorized"):
        with account_manager.test_accounts.use_sender(not_owner):
            solidity_contract_instance.setNumber(2)

    assert account_manager.default_sender is None
