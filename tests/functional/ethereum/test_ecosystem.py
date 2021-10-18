from ape_ethereum.ecosystem import Transaction


class TestTransaction:
    def test_as_dict_excludes_none_values(self):
        txn = Transaction()
        txn.value = 1000000
        actual = txn.as_dict()
        assert "value" in actual
        txn.value = None
        actual = txn.as_dict()
        assert "value" not in actual
