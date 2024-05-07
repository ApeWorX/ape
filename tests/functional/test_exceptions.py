import re

from ape.api import ReceiptAPI
from ape.exceptions import Abort, NetworkNotFoundError, TransactionError
from ape_ethereum.transactions import Receipt


def test_abort():
    expected = re.compile(r"Operation aborted in test_exceptions.py::test_abort on line \d+\.")
    assert expected.match(str(Abort()))


def test_transaction_error_when_receipt_is_subclass(vyper_contract_instance, owner):
    """
    Ensure TransactionError knows subclass Receipts are still receipts.
    (There was a bug once when it didn't, and that caused internal AttributeErrors).
    """

    class SubclassReceipt(Receipt):
        pass

    receipt = vyper_contract_instance.setNumber(123, sender=owner)
    receipt_data = {**receipt.model_dump(), "transaction": receipt.transaction}
    sub_receipt = SubclassReceipt.model_validate(receipt_data)

    err = TransactionError(txn=sub_receipt)
    assert isinstance(err.txn, ReceiptAPI)  # Same check used.


def test_network_not_found_error_close_match():
    net = "sepolai"
    error = NetworkNotFoundError(net, ecosystem="ethereum", options=("sepolia",))
    actual = str(error)
    expected = f"No network in 'ethereum' named '{net}'. Did you mean 'sepolia'?"
    assert actual == expected


def test_network_not_found_error_no_close_matches():
    net = "madeup"
    error = NetworkNotFoundError(net, ecosystem="ethereum", options=("sepolia",))
    actual = str(error)
    expected = f"No network in 'ethereum' named '{net}'. Options:\nsepolia"
    assert actual == expected


def test_network_with_ecosystem_not_found_no_options():
    net = "madeup"
    error = NetworkNotFoundError(net, ecosystem="ethereum", options=())
    actual = str(error)
    expected = "'ethereum' has no networks."
    assert actual == expected


def test_network_without_ecosystem_not_found_no_options():
    net = "madeup"
    error = NetworkNotFoundError(net, options=())
    actual = str(error)
    expected = "No networks found."
    assert actual == expected
