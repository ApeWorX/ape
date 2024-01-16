from ape_ethereum.transactions import TransactionType
from tests.conftest import geth_process_test


@geth_process_test
def test_default_transaction_type_configured_from_custom_network(
    custom_network_connection, ethereum
):
    assert ethereum.default_transaction_type == TransactionType.STATIC
