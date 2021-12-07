import pytest

from ape.api import TransactionAPI, TransactionType
from ape.api.accounts import AccountAPI
from ape.exceptions import AccountsError
from ape.types import AddressType

from ..conftest import TEST_ADDRESS


class _TestAccountAPI(AccountAPI):
    can_sign: bool

    @property
    def address(self):
        return AddressType(TEST_ADDRESS)

    def sign_message(self, msg):
        return "test-signature" if self.can_sign else None

    def sign_transaction(self, txn):
        return "test-signature" if self.can_sign else None


@pytest.fixture
def test_account_api_no_sign(mock_account_container_api, mock_provider_api):
    account = _TestAccountAPI(mock_account_container_api, can_sign=False)
    account._provider = mock_provider_api
    return account


@pytest.fixture
def test_account_api_can_sign(mock_account_container_api, mock_provider_api):
    account = _TestAccountAPI(mock_account_container_api, can_sign=True)
    account._provider = mock_provider_api
    return account


class TestAccountAPI:
    def test_txn_nonce_less_than_accounts_raises_tx_error(
        self, mocker, mock_provider_api, test_account_api_can_sign
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)

        # Differing nonces
        mock_provider_api.get_nonce.return_value = 1
        mock_transaction.nonce = 0

        with pytest.raises(AccountsError) as err:
            test_account_api_can_sign.call(mock_transaction)

        assert str(err.value) == "Invalid nonce, will not publish."

    def test_not_enough_funds_raises_error(
        self, mocker, mock_provider_api, test_account_api_can_sign
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)
        mock_provider_api.get_nonce.return_value = mock_transaction.nonce = 0
        mock_transaction.type = TransactionType.STATIC
        mock_transaction.gas_price = 0

        # Transaction costs are greater than balance
        mock_transaction.total_transfer_value = 1000000
        mock_provider_api.get_balance.return_value = 0

        with pytest.raises(AccountsError) as err:
            test_account_api_can_sign.call(mock_transaction)

        expected = (
            "Transfer value meets or exceeds account balance.\n"
            "Are you using the correct provider/account combination?\n"
            "(transfer_value=1000000, balance=0)."
        )
        assert str(err.value) == expected

    def test_transaction_not_signed_raises_error(
        self, mocker, mock_provider_api, test_account_api_no_sign
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)
        mock_provider_api.get_nonce.return_value = mock_transaction.nonce = 0
        mock_transaction.total_transfer_value = mock_provider_api.get_balance.return_value = 1000000
        mock_transaction.type = TransactionType.STATIC
        mock_transaction.gas_price = 0
        mock_transaction.required_confirmations = 0

        with pytest.raises(AccountsError) as err:
            test_account_api_no_sign.call(mock_transaction)

        assert str(err.value) == "The transaction was not signed."

    def test_call_when_no_gas_limit_calls_estimate_gas_cost(
        self, mocker, mock_provider_api, test_account_api_can_sign
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)
        mock_transaction.type = TransactionType.STATIC
        mock_transaction.required_confirmations = 0
        mock_transaction.gas_price = 0
        mock_transaction.gas_limit = None  # Causes estimate_gas_cost to get called
        mock_provider_api.get_nonce.return_value = mock_transaction.nonce = 0
        mock_transaction.total_transfer_value = mock_provider_api.get_balance.return_value = 1000000
        mock_transaction.signature.return_value = "test-signature"
        test_account_api_can_sign.call(mock_transaction)
        mock_provider_api.estimate_gas_cost.assert_called_once_with(mock_transaction)

    def test_call_sets_required_confirmations(
        self, mocker, mock_provider_api, test_account_api_can_sign
    ):
        mock_transaction = mocker.MagicMock(spec=TransactionAPI)
        mock_transaction.type = TransactionType.STATIC
        mock_transaction.gas_price = 0
        mock_provider_api.get_nonce.return_value = mock_transaction.nonce = 0
        mock_transaction.total_transfer_value = mock_provider_api.get_balance.return_value = 1000000
        mock_transaction.required_confirmations = None  # To be explicit

        expected_required_confirmations = 12
        mock_provider_api.network.required_confirmations = expected_required_confirmations
        mock_transaction.required_confirmations = None
        test_account_api_can_sign.call(mock_transaction)
        assert mock_transaction.required_confirmations == expected_required_confirmations
