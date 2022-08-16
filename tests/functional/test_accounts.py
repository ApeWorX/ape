import pytest
from eip712.messages import EIP712Message
from eth_account.messages import encode_defunct

import ape
from ape import convert
from ape.exceptions import AccountsError, ContractLogicError, SignatureError, TransactionError

MISSING_VALUE_TRANSFER_ERR_MSG = "Must provide 'VALUE' or use 'send_everything=True"


@pytest.fixture(autouse=True, scope="module")
def connected(eth_tester_provider):
    yield


@pytest.fixture
def signer(test_accounts):
    return test_accounts[2]


class Foo(EIP712Message):
    _name_: "string" = "Foo"  # type: ignore  # noqa: F821
    bar: "address"  # type: ignore  # noqa: F821


def test_sign_message(signer):
    message = encode_defunct(text="Hello Apes!")
    signature = signer.sign_message(message)
    assert signer.check_signature(message, signature)


def test_sign_eip712_message(signer):
    message = Foo(signer.address).signable_message
    signature = signer.sign_message(message)
    assert signer.check_signature(message, signature)


def test_sign_message_with_prompts(runner, keyfile_account):
    # "y\na\ny": yes sign, password, yes keep unlocked
    with runner.isolation(input="y\na\ny"):
        message = encode_defunct(text="Hello Apes!")
        signature = keyfile_account.sign_message(message)
        assert keyfile_account.check_signature(message, signature)

    # # "n": don't sign
    with runner.isolation(input="n\n"):
        signature = keyfile_account.sign_message(message)
        assert signature is None


def test_transfer(sender, receiver):
    initial_balance = receiver.balance
    sender.transfer(receiver, "1 gwei")
    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected


def test_transfer_without_value(sender, receiver):
    with pytest.raises(AccountsError, match=MISSING_VALUE_TRANSFER_ERR_MSG):
        sender.transfer(receiver)


def test_transfer_without_value_send_everything_false(sender, receiver):
    with pytest.raises(AccountsError, match=MISSING_VALUE_TRANSFER_ERR_MSG):
        sender.transfer(receiver, send_everything=False)


def test_transfer_without_value_send_everything_true(sender, receiver, isolation):
    # Clear balance of sender
    sender.transfer(receiver, send_everything=True)

    expected_err_regex = r"Sender does not have enough to cover transaction value and gas: \d*"
    with pytest.raises(AccountsError, match=expected_err_regex):
        sender.transfer(receiver, send_everything=True)


def test_transfer_with_value_send_everything_true(sender, receiver, isolation):
    with pytest.raises(AccountsError, match="Cannot use 'send_everything=True' with 'VALUE'."):
        sender.transfer(receiver, 1, send_everything=True)


def test_transfer_with_prompts(runner, receiver, keyfile_account):
    # "y\na\ny": yes sign, password, yes keep unlocked
    with runner.isolation("y\na\ny"):
        receipt = keyfile_account.transfer(receiver, "1 gwei")
        assert receipt.receiver == receiver

    # "n": don't sign
    with runner.isolation(input="n\n"):
        with pytest.raises(SignatureError):
            keyfile_account.transfer(receiver, "1 gwei")


def test_transfer_using_type_0(sender, receiver):
    initial_balance = receiver.balance
    sender.transfer(receiver, "1 gwei", type=0)
    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected


def test_deploy(owner, contract_container, chain, clean_contracts_cache):
    contract = owner.deploy(contract_container)
    assert contract.address
    assert contract.txn_hash

    # Deploy again to prove that we get the correct txn_hash below
    owner.deploy(contract_container)

    # Verify can reload same contract from cache
    contract_from_cache = ape.Contract(contract.address)
    assert contract_from_cache.contract_type == contract.contract_type
    assert contract_from_cache.address == contract.address
    assert contract_from_cache.txn_hash == contract.txn_hash


def test_contract_calls(owner, contract_instance):
    contract_instance.setNumber(2, sender=owner)
    assert contract_instance.myNumber() == 2


def test_contract_revert(sender, contract_instance):
    # 'sender' is not the owner so it will revert (with a message)
    with pytest.raises(ContractLogicError) as err:
        contract_instance.setNumber(5, sender=sender)

    assert str(err.value) == "!authorized"


def test_contract_revert_no_message(owner, contract_instance):
    # The Contract raises empty revert when setting number to 5.
    with pytest.raises(ContractLogicError) as err:
        contract_instance.setNumber(5, sender=owner)

    assert str(err.value) == "Transaction failed."  # Default message


def test_send_transaction_with_bad_nonce(sender, receiver):
    # Bump the nonce so we can set one that is too low.
    sender.transfer(receiver, "1 gwei", type=0)

    with pytest.raises(AccountsError) as err:
        sender.transfer(receiver, "1 gwei", type=0, nonce=0)

    assert str(err.value) == "Invalid nonce, will not publish."


def test_send_transaction_without_enough_funds(sender, receiver):
    with pytest.raises(TransactionError) as err:
        sender.transfer(receiver, "10000000000000 ETH")

    assert "Sender does not have enough balance to cover" in str(err.value)


def test_send_transaction_sets_defaults(sender, receiver):
    receipt = sender.transfer(receiver, "1 GWEI", gas_limit=None, required_confirmations=None)
    assert receipt.gas_limit > 0
    assert receipt.required_confirmations == 0


def test_accounts_splice_access(test_accounts):
    a, b = test_accounts[:2]
    assert a == test_accounts[0]
    assert b == test_accounts[1]
    c = test_accounts[-1]
    assert c == test_accounts[len(test_accounts) - 1]
    assert len(test_accounts[::2]) == len(test_accounts) / 2


def test_accounts_address_access(test_accounts, accounts):
    assert accounts[test_accounts[0].address] == test_accounts[0]


def test_accounts_contains(accounts, test_accounts):
    assert test_accounts[0].address in accounts


def test_autosign_messages(runner, keyfile_account):
    keyfile_account.set_autosign(True, passphrase="a")
    message = encode_defunct(text="Hello Apes!")
    signature = keyfile_account.sign_message(message)
    assert keyfile_account.check_signature(message, signature)

    # Re-enable prompted signing
    keyfile_account.set_autosign(False)
    with runner.isolation(input="y\na\n"):
        signature = keyfile_account.sign_message(message)
        assert keyfile_account.check_signature(message, signature)


def test_autosign_transactions(runner, keyfile_account, receiver):
    keyfile_account.set_autosign(True, passphrase="a")
    assert keyfile_account.transfer(receiver, "1 gwei")

    # Re-enable prompted signing
    keyfile_account.set_autosign(False)
    with runner.isolation(input="y\na\n"):
        assert keyfile_account.transfer(receiver, "1 gwei")


def test_impersonate_not_implemented(accounts):
    test_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    with pytest.raises(IndexError) as err:
        _ = accounts[test_address]

    expected_err_msg = (
        "Your provider does not support impersonating accounts:\n"
        f"No account with address '{test_address}'."
    )
    assert expected_err_msg in str(err.value)


def test_contract_as_sender_non_fork_network(contract_instance):
    with pytest.raises(IndexError) as err:
        contract_instance.setNumber(5, sender=contract_instance)

    expected_err_msg = (
        "Your provider does not support impersonating accounts:\n"
        f"No account with address '{contract_instance}'."
    )
    assert expected_err_msg in str(err.value)


def test_unlock_with_passphrase_and_sign_message(runner, keyfile_account):
    keyfile_account.unlock(passphrase="a")
    message = encode_defunct(text="Hello Apes!")

    # y: yes, sign (note: unlocking makes the key available but is not the same as autosign).
    with runner.isolation(input="y\n"):
        signature = keyfile_account.sign_message(message)
        assert keyfile_account.check_signature(message, signature)


def test_unlock_from_prompt_and_sign_message(runner, keyfile_account):
    # a = password
    with runner.isolation(input="a\n"):
        keyfile_account.unlock()
        message = encode_defunct(text="Hello Apes!")

    # yes, sign the message
    with runner.isolation(input="y\n"):
        signature = keyfile_account.sign_message(message)
        assert keyfile_account.check_signature(message, signature)


def test_unlock_with_passphrase_and_sign_transaction(runner, keyfile_account, receiver):
    keyfile_account.unlock(passphrase="a")
    # y: yes, sign (note: unlocking makes the key available but is not the same as autosign).
    with runner.isolation(input="y\n"):
        receipt = keyfile_account.transfer(receiver, "1 gwei")
        assert receipt.receiver == receiver


def test_unlock_from_prompt_and_sign_transaction(runner, keyfile_account, receiver):
    # a = password
    with runner.isolation(input="a\n"):
        keyfile_account.unlock()

    # yes, sign the transaction
    with runner.isolation(input="y\n"):
        receipt = keyfile_account.transfer(receiver, "1 gwei")
        assert receipt.receiver == receiver


def test_custom_num_of_test_accts_config(test_accounts, temp_config):
    from ape.utils.testing import DEFAULT_NUMBER_OF_TEST_ACCOUNTS

    CUSTOM_NUMBER_OF_TEST_ACCOUNTS = 20

    test_config = {
        "test": {
            "number_of_accounts": CUSTOM_NUMBER_OF_TEST_ACCOUNTS,
        }
    }

    assert len(test_accounts) == DEFAULT_NUMBER_OF_TEST_ACCOUNTS

    with temp_config(test_config):
        assert len(test_accounts) == CUSTOM_NUMBER_OF_TEST_ACCOUNTS


def test_test_accounts_repr(test_accounts):
    actual = repr(test_accounts)
    assert all(a.address in actual for a in test_accounts)
