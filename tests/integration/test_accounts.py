from eth_account import Account
from eth_account.messages import encode_defunct

from ape import accounts, convert


def test_sign_message(test_accounts):
    signer = test_accounts[2]
    message = encode_defunct(text="Hello Apes!")
    signature = signer.sign_message(message).encode_rsv()
    signer_address = Account.recover_message(message, signature=signature)
    assert signer_address == signer.address


def test_transfer(eth_tester_provider, sender, receiver):
    sender = accounts.test_accounts[0]
    receiver = accounts.test_accounts[1]
    initial_balance = receiver.balance

    sender.transfer(receiver, "1 gwei")

    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected
