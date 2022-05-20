import json

import pytest
from eth_account.messages import encode_defunct

import ape
from ape import convert
from ape.exceptions import AccountsError, ContractLogicError, SignatureError, TransactionError

ALIAS = "__FUNCTIONAL_TESTS_ALIAS__"


@pytest.fixture(autouse=True, scope="module")
def connected(eth_tester_provider):
    yield


@pytest.fixture
def temp_ape_account(sender, keyparams, temp_accounts_path):
    test_keyfile_path = temp_accounts_path / f"{ALIAS}.json"

    if test_keyfile_path.exists():
        # Corrupted from a previous test
        test_keyfile_path.unlink()

    test_keyfile_path.write_text(json.dumps(keyparams))

    acct = ape.accounts.load(ALIAS)
    sender.transfer(acct, "1 ETH")  # Auto-fund this account
    yield acct

    if test_keyfile_path.exists():
        test_keyfile_path.unlink()


def test_sign_message(test_accounts):
    signer = test_accounts[2]
    message = encode_defunct(text="Hello Apes!")
    signature = signer.sign_message(message)
    assert signer.check_signature(message, signature)


def test_sign_message_with_prompts(runner, temp_ape_account):
    # "y\na\ny": yes sign, password, yes keep unlocked
    with runner.isolation(input="y\na\ny"):
        message = encode_defunct(text="Hello Apes!")
        signature = temp_ape_account.sign_message(message)
        assert temp_ape_account.check_signature(message, signature)

    # # "n": don't sign
    with runner.isolation(input="n\n"):
        signature = temp_ape_account.sign_message(message)
        assert signature is None


def test_transfer(sender, receiver):
    initial_balance = receiver.balance
    sender.transfer(receiver, "1 gwei")
    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected


def test_transfer_without_value(sender, receiver):
    with pytest.raises(ValueError) as err:
        sender.transfer(receiver)
    assert str(err.value) == "Transfer without value argument requires kwarg send_everything=True"


def test_transfer_without_value_send_everything_false(sender, receiver):
    with pytest.raises(ValueError) as err:
        sender.transfer(receiver, send_everything=False)
    assert str(err.value) == "Transfer without value argument requires kwarg send_everything=True"


def test_transfer_without_value_send_everything_true(sender, receiver):
    initial_balance = receiver.balance
    sender.transfer(receiver, send_everything=True)
    assert receiver.balance > initial_balance, "Receiver has same balance after transfer"
    assert sender.balance < convert("1 finney", int), "Sender balance is not nominal"
    with pytest.raises(ValueError) as err:
        sender.transfer(receiver, send_everything=True)
    assert "Sender does not have enough to cover transaction value and gas:" in str(err.value)


def test_transfer_with_value_send_everything_true(sender, receiver):
    with pytest.raises(ValueError) as err:
        sender.transfer(receiver, 1, send_everything=True)
    assert str(err.value) == "Kwarg send_everything=True requires transfer without value argument"


def test_transfer_with_prompts(runner, receiver, temp_ape_account):
    # "y\na\ny": yes sign, password, yes keep unlocked
    with runner.isolation("y\na\ny"):
        receipt = temp_ape_account.transfer(receiver, "1 gwei")
        assert receipt.receiver == receiver

    # "n": don't sign
    with runner.isolation(input="n\n"):
        with pytest.raises(SignatureError):
            temp_ape_account.transfer(receiver, "1 gwei")


def test_transfer_using_type_0(sender, receiver):
    initial_balance = receiver.balance
    sender.transfer(receiver, "1 gwei", type=0)
    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected


def test_deploy(owner, contract_container, chain, clean_contracts_cache):
    contract = owner.deploy(contract_container)
    assert contract.address

    # Verify can reload same contract from cache
    contract_from_cache = ape.Contract(contract.address)
    assert contract_from_cache.contract_type == contract.contract_type
    assert contract_from_cache.address == contract.address


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


def test_autosign_messages(temp_ape_account):
    temp_ape_account.set_autosign(True, passphrase="a")
    message = encode_defunct(text="Hello Apes!")
    signature = temp_ape_account.sign_message(message)
    assert temp_ape_account.check_signature(message, signature)


def test_autosign_transactions(temp_ape_account, receiver):
    temp_ape_account.set_autosign(True, passphrase="a")
    assert temp_ape_account.transfer(receiver, "1 gwei")


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


def test_unlock_with_passphrase_and_sign_message(runner, temp_ape_account):
    temp_ape_account.unlock(passphrase="a")
    message = encode_defunct(text="Hello Apes!")

    # y: yes, sign (note: unlocking makes the key available but is not the same as autosign).
    with runner.isolation(input="y\n"):
        signature = temp_ape_account.sign_message(message)
        assert temp_ape_account.check_signature(message, signature)


def test_unlock_from_prompt_and_sign_message(runner, temp_ape_account):
    # a = password
    with runner.isolation(input="a\n"):
        temp_ape_account.unlock()
        message = encode_defunct(text="Hello Apes!")

    # yes, sign the message
    with runner.isolation(input="y\n"):
        signature = temp_ape_account.sign_message(message)
        assert temp_ape_account.check_signature(message, signature)


def test_unlock_with_passphrase_and_sign_transaction(runner, temp_ape_account, receiver):
    temp_ape_account.unlock(passphrase="a")
    # y: yes, sign (note: unlocking makes the key available but is not the same as autosign).
    with runner.isolation(input="y\n"):
        receipt = temp_ape_account.transfer(receiver, "1 gwei")
        assert receipt.receiver == receiver


def test_unlock_from_prompt_and_sign_transaction(runner, temp_ape_account, receiver):
    # a = password
    with runner.isolation(input="a\n"):
        temp_ape_account.unlock()

    # yes, sign the transaction
    with runner.isolation(input="y\n"):
        receipt = temp_ape_account.transfer(receiver, "1 gwei")
        assert receipt.receiver == receiver
