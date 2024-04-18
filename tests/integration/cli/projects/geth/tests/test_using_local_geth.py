import pytest


def test_provider(project, networks):
    """
    Tests that the network gets set from ape-config.yaml.
    """
    assert networks.provider.name == "node"
    assert networks.provider.is_connected


def test_extra_account(chain):
    """
    Show we can fund accounts from the config option.
    """
    addr = "0x63c7f11162dBFC374DC6f5C0B3Aa26C618846a85"
    actual = chain.provider.get_balance(addr)
    assert actual > 0


def test_contract_interaction(owner, contract):
    """
    Traditional ape-test style test.
    """
    contract.setNumber(999, sender=owner)
    assert contract.myNumber() == 999


def test_transfer(accounts):
    """
    Tests that the ReceiptCapture handles transfer transactions.
    """
    accounts[-1].transfer(accounts[-2], "100 gwei")


def test_using_contract_with_same_type_and_method_call(accounts, project):
    """
    Deploy the same contract from the ``contract`` fixture and call a method
    that gets called elsewhere in the test suite. This shows that we amass
    results across all instances of contract types when making the gas report.
    """

    owner = accounts[7]
    contract = project.VyperContract.deploy(sender=owner)
    contract.setNumber(777, sender=owner)
    assert contract.myNumber() == 777


def test_two_contracts_with_same_symbol(accounts, project):
    """
    Tests against scenario when using 2 tokens with same symbol.
    There was almost a bug where the contract IDs clashed.
    This is to help prevent future bugs related to this.
    """
    receiver = accounts[-1]
    sender = accounts[-2]
    token_a = project.TokenA.deploy(sender=sender)
    token_b = project.TokenB.deploy(sender=sender)
    token_a.transfer(receiver, 5, sender=sender)
    token_b.transfer(receiver, 6, sender=sender)
    assert token_a.balanceOf(receiver) == 5
    assert token_b.balanceOf(receiver) == 6


def test_call_method_excluded_from_cli_options(accounts, contract):
    """
    Call a method so that we can intentionally ignore it via command
    line options and test that it does not show in the report.
    """
    receipt = contract.fooAndBar(sender=accounts[9])
    assert not receipt.failed


def test_call_method_excluded_from_config(accounts, contract):
    """
    Call a method excluded in the ``ape-config.yaml`` file
    for asserting it does not show in gas report.
    """
    account = accounts[-4]
    receipt = contract.setAddress(account.address, sender=account)
    assert not receipt.failed


@pytest.mark.use_network("ethereum:local:test")
def test_switch_back_to_eth_tester(chain):
    """
    Test to verify the `use_network` marker works.
    This test is in the geth project because that is the only test project
    that has multiple providers.
    """
    assert chain.provider.name == "test"
