import pytest

from ape.exceptions import ContractLogicError, OutOfGasError
from tests.conftest import geth_process_test


@geth_process_test
def test_contract_interaction(geth_provider, geth_account, geth_contract, mocker):
    # Spy on the estimate_gas RPC method.
    estimate_gas_spy = mocker.spy(geth_provider.web3.eth, "estimate_gas")

    # Check what max gas is before transacting.
    max_gas = geth_provider.max_gas

    # Invoke a method from a contract via transacting.
    receipt = geth_contract.setNumber(102, sender=geth_account)

    # Verify values from the receipt.
    assert not receipt.failed
    assert receipt.receiver == geth_contract.address
    assert receipt.gas_used < receipt.gas_limit
    assert receipt.gas_limit == max_gas

    # Show contract state changed.
    assert geth_contract.myNumber() == 102

    # Verify the estimate gas RPC was not used (since we are using max_gas).
    assert estimate_gas_spy.call_count == 0


@geth_process_test
def test_revert(accounts, not_owner, geth_contract):
    # 'sender' is not the owner so it will revert (with a message)
    with pytest.raises(ContractLogicError, match="!authorized") as err:
        geth_contract.setNumber(5, sender=not_owner)

    assert err.value.txn is not None


@geth_process_test
def test_revert_no_message(accounts, geth_contract, geth_account):
    # The Contract raises empty revert when setting number to 5.
    expected = "Transaction failed."  # Default message
    with pytest.raises(ContractLogicError, match=expected) as err:
        geth_contract.setNumber(5, sender=geth_account)

    assert err.value.txn is not None


@geth_process_test
def test_revert_custom_error(error_contract_geth, geth_second_account):
    contract = error_contract_geth
    with pytest.raises(contract.Unauthorized) as err:
        contract.withdraw(sender=geth_second_account)

    assert err.value.txn is not None
    assert err.value.inputs == {"addr": geth_second_account.address, "counter": 123}


@geth_process_test
def test_revert_custom_error_deploy(error_contract_container, geth_account, chain, geth_provider):
    with pytest.raises(Exception) as err:
        geth_account.deploy(error_contract_container, 0)

    err_cls = err.value
    assert isinstance(err_cls, ContractLogicError)
    if err_cls.address:
        contract = chain.contracts.instance_at(err_cls.address)

        # Ensure it is the custom error.
        assert isinstance(err_cls, contract.OtherError)

    else:
        # skip this test - still covered in reverts() tests anyway.
        return


@geth_process_test
def test_revert_out_of_gas_error(geth_account, geth_second_account, geth_provider):
    """
    Attempt to transact with not quite enough gas. We should get an error saying
    we ran out of gas.
    """
    with pytest.raises(OutOfGasError) as err:
        geth_account.transfer(geth_second_account, 1, gas_limit=1)

    assert err.value.txn is not None
