from tests.conftest import geth_process_test


@geth_process_test
def test_contract_event(geth_contract, geth_account):
    geth_contract.setNumber(101010, sender=geth_account)
    actual = geth_contract.NumberChange[-1]
    assert actual.event_name == "NumberChange"
    assert actual.contract_address == geth_contract.address
    assert actual.event_arguments["newNum"] == 101010
