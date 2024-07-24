import re

import pytest

from ape.api import ReceiptAPI
from ape.exceptions import Abort, NetworkNotFoundError, TransactionError
from ape_ethereum.transactions import DynamicFeeTransaction, Receipt


@pytest.fixture(scope="module")
def failing_call():
    # A call (tx without sender)
    data = {
        "chainId": 1337,
        "to": "0x5FbDB2315678afecb367f032d93F642f64180aa3",
        "from": "0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266",
        "gas": 30029122,
        "value": 0,
        "data": "0xce50aa7d00000000000000000000000070997970c51812dc3a010c7d01b50e0d17dc79c80000000000000000000000000000000000000000000000000000000000000001",  # noqa: E501
        "type": 2,
        "maxFeePerGas": 875000000,
        "maxPriorityFeePerGas": 0,
        "accessList": [],
    }
    return DynamicFeeTransaction.model_validate(data)


class TestAbort:
    def test_shows_line_number(self):
        actual = str(Abort())
        expected = re.compile(r"Operation aborted in [\w<>.]*::[\w<>]* on line \d+\.")
        assert expected.match(actual)


class TestTransactionError:
    def test_receipt_is_subclass(self, vyper_contract_instance, owner):
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

    def test_address(self, owner):
        err = TransactionError(contract_address=owner.address)
        assert err.address == owner.address

    def test_receiver_as_address(self, owner):
        tx = owner.transfer(owner, "1 wei")
        err = TransactionError(txn=tx)
        assert err.address == owner.address

    def test_deploy_address_as_address(
        self, owner, ethereum, vyper_contract_container, zero_address
    ):
        contract = vyper_contract_container.deploy(629, sender=owner)

        receipt = contract.creation_metadata.receipt
        data = receipt.model_dump(exclude=("transaction",))
        # Show when receiver is zero_address, it still picks contract address.
        data["transaction"] = ethereum.create_transaction(receiver=zero_address)

        tx = Receipt.model_validate(data)
        assert tx.receiver == zero_address, "setup failed"

        err = TransactionError(txn=tx)
        assert err.address == contract.address

    def test_call_with_txn_and_not_source_tb(self, failing_call):
        """
        Simulating a failing-call, making sure it doesn't
        blow up if it doesn't get a source-tb.
        """
        err = TransactionError(txn=failing_call)
        assert err.source_traceback is None

    def test_call_with_source_tb_and_not_txn(self, mocker, project_with_contract):
        """
        Simulating a failing call, making sure the source-tb lines
        show up when a txn is NOT given.
        """
        # Using mocks for simplicity. Otherwise have to use a bunch of models from ethpm-types;
        # most of the stuff being mocked seems simple but is calculated from AST-Nodes and such.
        src_path = "path/to/VyperFile.vy"
        mock_tb = mocker.MagicMock()
        mock_exec = mocker.MagicMock()
        mock_exec.depth = 1
        mock_exec.source_path = src_path
        mock_exec.begin_lineno = 5
        mock_exec.end_lineno = 5
        mock_closure = mocker.MagicMock()
        mock_closure.name = "setNumber"
        mock_exec.closure = mock_closure
        mock_tb.__getitem__.return_value = mock_exec
        mock_tb.__len__.return_value = 1

        err = TransactionError(source_traceback=mock_tb, project=project_with_contract)

        # Have to raise for sys.exc_info() to be available.
        try:
            raise err
        except Exception:
            pass

        assert err.__traceback__ is not None

        # The Vyper-frame gets injected at tb_next.
        assert err.__traceback__.tb_next is not None

        actual = str(err.__traceback__.tb_next.tb_frame)
        assert src_path in actual


class TestNetworkNotFoundError:
    def test_close_match(self):
        net = "sepolai"
        error = NetworkNotFoundError(net, ecosystem="ethereum", options=("sepolia",))
        actual = str(error)
        expected = f"No network in 'ethereum' named '{net}'. Did you mean 'sepolia'?"
        assert actual == expected

    def test_no_close_matches(self):
        net = "madeup"
        error = NetworkNotFoundError(net, ecosystem="ethereum", options=("sepolia",))
        actual = str(error)
        expected = f"No network in 'ethereum' named '{net}'. Options:\nsepolia"
        assert actual == expected

    def test_ecosystem_no_network_options(self):
        net = "madeup"
        error = NetworkNotFoundError(net, ecosystem="ethereum", options=())
        actual = str(error)
        expected = "'ethereum' has no networks."
        assert actual == expected

    def test_no_options(self):
        net = "madeup"
        error = NetworkNotFoundError(net, options=())
        actual = str(error)
        expected = "No networks found."
        assert actual == expected
