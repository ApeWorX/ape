from eth_account import Account
from eth_account.messages import encode_defunct

from ape import accounts, convert


def test_sign_message(test_accounts):
    signer = test_accounts[2]
    message = "Hello Apes!"
    message_hash = encode_defunct(text=message)

    actual_signature = signer.sign_message(message_hash)
    actual_signature_bytes = actual_signature.encode_rsv()
    expected_signature = Account.sign_message(message_hash, signer._private_key)
    assert actual_signature_bytes == expected_signature.signature

    signer_address = Account.recover_message(message_hash, signature=actual_signature_bytes)
    assert signer_address == signer.address


def test_transfer(eth_tester_provider, sender, receiver):
    sender = accounts.test_accounts[0]
    receiver = accounts.test_accounts[1]
    initial_balance = receiver.balance

    sender.transfer(receiver, "1 gwei")

    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected
