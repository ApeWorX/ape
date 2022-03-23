import pytest
from eth_account.messages import encode_defunct

from ape import convert
from ape.exceptions import AccountsError, TransactionError


def test_sign_message(test_accounts):
    signer = test_accounts[2]
    message = encode_defunct(text="Hello Apes!")
    signature = signer.sign_message(message)
    assert signer.check_signature(message, signature)


def test_transfer(sender, receiver):
    initial_balance = receiver.balance
    sender.transfer(receiver, "1 gwei")
    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected


def test_transfer_using_type_0(sender, receiver):
    initial_balance = receiver.balance
    sender.transfer(receiver, "1 gwei", type=0)
    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected


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
