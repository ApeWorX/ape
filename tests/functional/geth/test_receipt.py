from ape.api import TraceAPI
from ape.utils import ManagerAccessMixin
from tests.conftest import geth_process_test


@geth_process_test
def test_return_value_list(geth_account, geth_contract):
    tx = geth_contract.getFilledArray.transact(sender=geth_account)
    assert tx.return_value == [1, 2, 3]


@geth_process_test
def test_return_value_nested_address_array(geth_account, geth_contract, zero_address):
    tx = geth_contract.getNestedAddressArray.transact(sender=geth_account)
    expected = [
        [geth_account.address, geth_account.address, geth_account.address],
        [zero_address, zero_address, zero_address],
    ]
    actual = tx.return_value
    assert actual == expected


@geth_process_test
def test_return_value_nested_struct_in_tuple(geth_account, geth_contract):
    tx = geth_contract.getNestedStructWithTuple1.transact(sender=geth_account)
    actual = tx.return_value
    assert actual[0].t.a == geth_account.address
    assert actual[0].foo == 1
    assert actual[1] == 1


@geth_process_test
def test_trace(geth_account, geth_contract):
    tx = geth_contract.getNestedStructWithTuple1.transact(sender=geth_account)
    assert isinstance(tx.trace, TraceAPI)


@geth_process_test
def test_track_gas(mocker, geth_account, geth_contract, gas_tracker):
    tx = geth_contract.getNestedStructWithTuple1.transact(sender=geth_account)
    mock_test_runner = mocker.MagicMock()
    mock_test_runner.gas_tracker = gas_tracker

    ManagerAccessMixin._test_runner = mock_test_runner

    try:
        tx.track_gas()
    finally:
        ManagerAccessMixin._test_runner = None

    report = gas_tracker.session_gas_report or {}
    contract_name = geth_contract.contract_type.name
    assert contract_name in report
    assert "getNestedStructWithTuple1" in report[contract_name]


@geth_process_test
def test_await_confirmations(geth_account, geth_contract):
    tx = geth_contract.setNumber(235921972943759, sender=geth_account)
    tx.await_confirmations()
    assert tx.confirmed


@geth_process_test
def test_await_confirmations_zero_confirmations(mocker, geth_account, geth_contract):
    """
    We still need to wait for the nonce to increase when required confirmations is 0.
    Otherwise, we sometimes ran into nonce-issues when transacting too fast with
    the same account.
    """
    tx = geth_contract.setNumber(545921972923759, sender=geth_account, required_confirmations=0)
    spy = mocker.spy(tx, "_await_sender_nonce_increment")
    tx.await_confirmations()
    assert tx.confirmed
    assert spy.call_count == 1
