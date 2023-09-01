import pytest

from ape.exceptions import ContractLogicError, OutOfGasError
from tests.conftest import geth_process_test


@geth_process_test
def test_contract_interaction(geth_account, geth_contract):
    geth_contract.setNumber(102, sender=geth_account)
    assert geth_contract.myNumber() == 102


@geth_process_test
def test_tx_revert(accounts, not_owner, geth_contract):
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
def test_custom_error(error_contract_geth, geth_second_account):
    contract = error_contract_geth
    with pytest.raises(contract.Unauthorized) as err:
        contract.withdraw(sender=geth_second_account)

    assert err.value.txn is not None
    assert err.value.inputs == {"addr": geth_second_account.address, "counter": 123}


@geth_process_test
def test_custom_error_on_deploy(error_contract_container, geth_account, chain, geth_provider):
    with pytest.raises(Exception) as err:
        geth_account.deploy(error_contract_container, 0)

    assert isinstance(err.value, ContractLogicError)
    if err.value.address:
        contract = chain.contracts.instance_at(err.value.address)

        # Ensure it is the custom error.
        assert isinstance(err.value, contract.OtherError)

    else:
        # skip this test - still covered in reverts() tests anyway.
        return


@geth_process_test
def test_out_of_gas_error(geth_contract, geth_account, geth_provider):
    """
    Attempt to transact with not quite enough gas. We should get an error saying
    we ran out of gas.
    """
    txn = geth_contract.setNumber.as_transaction(333, sender=geth_account)
    gas = geth_provider.estimate_gas_cost(txn)
    txn.gas_limit = gas - 1
    with pytest.raises(OutOfGasError) as err:
        geth_account.call(txn)

    assert err.value.txn is not None
