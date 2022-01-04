from ape import convert


def test_transfer(networks_connected_to_tester, sender, receiver):
    initial_balance = receiver.balance
    sender.transfer(receiver, "1 gwei")
    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected
