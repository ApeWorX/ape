import re

from ape.api import ReceiptAPI
from ape.exceptions import Abort, NetworkNotFoundError, TransactionError
from ape_ethereum.transactions import Receipt


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
        # Show when receier is zero_address, it still picks contract address.
        data["transaction"] = ethereum.create_transaction(receiver=zero_address)

        tx = Receipt.model_validate(data)
        assert tx.receiver == zero_address, "setup failed"

        err = TransactionError(txn=tx)
        assert err.address == contract.address


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
