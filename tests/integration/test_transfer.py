from ape import accounts, convert


def test_transfer(in_test_network):
    sender = accounts.test_accounts[0]
    receiver = accounts.test_accounts[1]
    initial_balance = receiver.balance

    sender.transfer(receiver, "1 gwei")

    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected
