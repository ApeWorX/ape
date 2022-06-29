import pytest


@pytest.fixture
def invoke_receipt(solidity_contract_instance, owner):
    return solidity_contract_instance.setNumber(1, sender=owner)


def test_show_trace(invoke_receipt):
    # For better tests, see a provider plugin that supports this RPC,
    # such as ape-hardhat.
    with pytest.raises(NotImplementedError):
        invoke_receipt.show_trace()
