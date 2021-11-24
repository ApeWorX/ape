from ape import accounts, networks


def test_transfer():
    with networks.parse_network_choice("::test"):
        sender = accounts.test_accounts[0]
        receiver = accounts.test_accounts[1]
        sender.transfer(receiver, "1 gwei")
