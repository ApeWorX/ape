from os import environ

import pytest
from eip712.messages import EIP712Message
from eth_account.messages import encode_defunct

import ape
from ape.api import ImpersonatedAccount
from ape.exceptions import AccountsError, NetworkError, ProjectError, SignatureError
from ape.types import AutoGasLimit
from ape.types.signatures import recover_signer
from ape.utils.testing import DEFAULT_NUMBER_OF_TEST_ACCOUNTS
from ape_ethereum.ecosystem import ProxyType
from ape_ethereum.transactions import TransactionType
from ape_test.accounts import TestAccount
from tests.conftest import explorer_test

# NOTE: Even though `__test__` is set to `False` on the class,
# it must be set here as well for it to properly work for some reason.
TestAccount.__test__ = False

MISSING_VALUE_TRANSFER_ERR_MSG = "Must provide 'VALUE' or use 'send_everything=True"

APE_TEST_PATH = "ape_test.accounts.TestAccount"
APE_ACCOUNTS_PATH = "ape_accounts.accounts.KeyfileAccount"

PASSPHRASE = "a"
INVALID_PASSPHRASE = "incorrect passphrase"


@pytest.fixture(params=(APE_TEST_PATH, APE_ACCOUNTS_PATH))
def core_account(request, owner, keyfile_account):
    if request.param == APE_TEST_PATH:
        yield owner  # from ape_test plugin

    elif request.param == APE_ACCOUNTS_PATH:
        yield keyfile_account  # from ape_accounts plugin


class Foo(EIP712Message):
    _name_: "string" = "Foo"  # type: ignore  # noqa: F821
    bar: "address"  # type: ignore  # noqa: F821


def test_sign_message(signer):
    message = encode_defunct(text="Hello Apes!")
    signature = signer.sign_message(message)
    assert signer.check_signature(message, signature)


def test_recover_signer(signer):
    message = encode_defunct(text="Hello Apes!")
    signature = signer.sign_message(message)
    assert recover_signer(message, signature) == signer


def test_sign_eip712_message(signer):
    foo = Foo(signer.address)  # type: ignore
    message = foo.signable_message
    signature = signer.sign_message(message)
    assert signer.check_signature(message, signature)


def test_sign_message_with_prompts(runner, keyfile_account):
    # "y\na\ny": yes sign, password, yes keep unlocked
    start_nonce = keyfile_account.nonce
    with runner.isolation(input="y\na\ny"):
        message = encode_defunct(text="Hello Apes!")
        signature = keyfile_account.sign_message(message)
        assert keyfile_account.check_signature(message, signature)

    # # "n": don't sign
    with runner.isolation(input="n\n"):
        signature = keyfile_account.sign_message(message)
        assert signature is None

    # Nonce should not change from signing messages.
    end_nonce = keyfile_account.nonce
    assert start_nonce == end_nonce


def test_transfer(sender, receiver, eth_tester_provider, convert):
    initial_receiver_balance = receiver.balance
    initial_sender_balance = sender.balance
    value_str = "24 gwei"
    value_int = convert(value_str, int)

    receipt = sender.transfer(receiver, value_str)

    # Ensure each account balance was affected accordingly
    expected_receiver_balance = initial_receiver_balance + value_int
    expected_sender_loss = receipt.total_fees_paid + value_int
    expected_sender_balance = initial_sender_balance - expected_sender_loss
    assert receiver.balance == expected_receiver_balance
    assert (
        sender.balance == expected_sender_balance
    ), f"difference: {abs(sender.balance - expected_sender_balance)}"


def test_transfer_with_negative_value(sender, receiver):
    with pytest.raises(AccountsError, match="Value cannot be negative."):
        sender.transfer(receiver, value=-1)


def test_transfer_without_value(sender, receiver):
    with pytest.raises(AccountsError, match=MISSING_VALUE_TRANSFER_ERR_MSG):
        sender.transfer(receiver)


def test_transfer_without_value_send_everything_false(sender, receiver):
    with pytest.raises(AccountsError, match=MISSING_VALUE_TRANSFER_ERR_MSG):
        sender.transfer(receiver, send_everything=False)


def test_transfer_without_value_send_everything_true_with_low_gas(sender, receiver):
    initial_receiver_balance = receiver.balance
    initial_sender_balance = sender.balance

    # Clear balance of sender.
    # Use small gas so for sure runs out of money.
    receipt = sender.transfer(receiver, send_everything=True, gas=21000)

    value_given = receipt.value
    total_spent = value_given + receipt.total_fees_paid
    assert sender.balance == initial_sender_balance - total_spent
    assert receiver.balance == initial_receiver_balance + value_given

    expected_err_regex = r"Sender does not have enough to cover transaction value and gas: \d*"
    with pytest.raises(AccountsError, match=expected_err_regex):
        sender.transfer(receiver, send_everything=True)


def test_transfer_without_value_send_everything_true_with_high_gas(sender, receiver):
    initial_receiver_balance = receiver.balance
    initial_sender_balance = sender.balance

    # The gas selected here is very high compared to what actually gets used.
    gas = 25000000

    # Clear balance of sender
    receipt = sender.transfer(receiver, send_everything=True, gas=gas)

    value_given = receipt.value
    total_spent = value_given + receipt.total_fees_paid
    assert sender.balance == initial_sender_balance - total_spent
    assert receiver.balance == initial_receiver_balance + value_given

    # The sender is able to transfer again because they have so much left over
    # from safely using such a high gas before.
    # Use smaller (more expected) amount of gas this time.
    sender.transfer(receiver, send_everything=True, gas=21000)


def test_transfer_with_value_send_everything_true(sender, receiver):
    with pytest.raises(AccountsError, match="Cannot use 'send_everything=True' with 'VALUE'."):
        sender.transfer(receiver, 1, send_everything=True)


def test_transfer_with_prompts(runner, receiver, keyfile_account):
    # "y\na\ny": yes sign, password, yes keep unlocked
    with runner.isolation("y\na\ny"):
        receipt = keyfile_account.transfer(receiver, "1 gwei")
        assert receipt.receiver == receiver

    # "n": don't sign
    with runner.isolation(input="n\n"):
        with pytest.raises(SignatureError):
            keyfile_account.transfer(receiver, "1 gwei")


def test_transfer_using_type_0(sender, receiver, convert):
    initial_balance = receiver.balance
    sender.transfer(receiver, "1 gwei", type=0)
    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected


def test_deploy(owner, contract_container, chain, clean_contracts_cache):
    contract = owner.deploy(contract_container, 0)
    assert contract.address
    assert contract.txn_hash

    # Deploy again to prove that we get the correct txn_hash below
    owner.deploy(contract_container, 0)

    # Verify can reload same contract from cache
    contract_from_cache = ape.Contract(contract.address)
    assert contract_from_cache.contract_type == contract.contract_type
    assert contract_from_cache.address == contract.address
    assert contract_from_cache.txn_hash == contract.txn_hash


@explorer_test
def test_deploy_and_publish_local_network(owner, contract_container):
    with pytest.raises(ProjectError, match="Can only publish deployments on a live network"):
        owner.deploy(contract_container, 0, publish=True)


@explorer_test
def test_deploy_and_publish_live_network_no_explorer(owner, contract_container, dummy_live_network):
    dummy_live_network.__dict__["explorer"] = None
    expected_message = "Unable to publish contract - no explorer plugin installed."
    with pytest.raises(NetworkError, match=expected_message):
        owner.deploy(contract_container, 0, publish=True, required_confirmations=0)


@explorer_test
def test_deploy_and_publish(mocker, owner, contract_container, dummy_live_network):
    mock_explorer = mocker.MagicMock()
    dummy_live_network.__dict__["explorer"] = mock_explorer
    contract = owner.deploy(contract_container, 0, publish=True, required_confirmations=0)
    mock_explorer.publish_contract.assert_called_once_with(contract.address)


@explorer_test
def test_deploy_and_not_publish(mocker, owner, contract_container, dummy_live_network):
    mock_explorer = mocker.MagicMock()
    dummy_live_network.__dict__["explorer"] = mock_explorer
    owner.deploy(contract_container, 0, publish=True, required_confirmations=0)
    assert not mock_explorer.call_count


def test_deploy_proxy(owner, vyper_contract_instance, proxy_contract_container, chain):
    target = vyper_contract_instance.address
    proxy = owner.deploy(proxy_contract_container, target)
    assert proxy.address in chain.contracts._local_contract_types
    assert proxy.address in chain.contracts._local_proxies

    actual = chain.contracts._local_proxies[proxy.address]
    assert actual.target == target
    assert actual.type == ProxyType.Delegate

    # Show we get the implementation contract type using the proxy address
    implementation = chain.contracts.instance_at(proxy.address)
    assert implementation.contract_type == vyper_contract_instance.contract_type


def test_send_transaction_with_bad_nonce(sender, receiver):
    # Bump the nonce so we can set one that is too low.
    sender.transfer(receiver, "1 gwei", type=0)

    with pytest.raises(AccountsError, match="Invalid nonce, will not publish."):
        sender.transfer(receiver, "1 gwei", type=0, nonce=0)


def test_send_transaction_without_enough_funds(sender, receiver):
    with pytest.raises(AccountsError, match="Transfer value meets or exceeds account balance"):
        sender.transfer(receiver, "10000000000000 ETH")


def test_send_transaction_sets_defaults(sender, receiver):
    receipt = sender.transfer(receiver, "1 GWEI", gas_limit=None, required_confirmations=None)
    assert receipt.gas_limit > 0
    assert receipt.required_confirmations == 0


def test_accounts_splice_access(test_accounts):
    a, b = test_accounts[:2]
    assert a == test_accounts[0]
    assert b == test_accounts[1]
    c = test_accounts[-1]
    assert c == test_accounts[len(test_accounts) - 1]
    assert len(test_accounts[::2]) == len(test_accounts) / 2


def test_accounts_address_access(owner, accounts):
    assert accounts[owner.address] == owner


def test_accounts_contains(accounts, owner):
    assert owner.address in accounts


def test_autosign_messages(runner, keyfile_account):
    keyfile_account.set_autosign(True, passphrase="a")
    message = encode_defunct(text="Hello Apes!")
    signature = keyfile_account.sign_message(message)
    assert keyfile_account.check_signature(message, signature)

    # Re-enable prompted signing
    keyfile_account.set_autosign(False)
    with runner.isolation(input="y\na\n"):
        signature = keyfile_account.sign_message(message)
        assert keyfile_account.check_signature(message, signature)


def test_autosign_transactions(runner, keyfile_account, receiver):
    keyfile_account.set_autosign(True, passphrase="a")
    assert keyfile_account.transfer(receiver, "1 gwei")

    # Re-enable prompted signing
    keyfile_account.set_autosign(False)
    with runner.isolation(input="y\na\n"):
        assert keyfile_account.transfer(receiver, "1 gwei")


def test_impersonate_not_implemented(accounts, address):
    expected_err_msg = (
        "Your provider does not support impersonating accounts:\n"
        f"No account with address '{address}'."
    )
    with pytest.raises(IndexError, match=expected_err_msg):
        _ = accounts[address]


def test_impersonated_account_ignores_signature_check_on_txn(accounts, address):
    account = ImpersonatedAccount(raw_address=address)

    # Impersonate hack, since no providers in core actually support it.
    accounts.test_accounts._impersonated_accounts[address] = account
    other_0 = accounts.test_accounts[8]
    other_1 = accounts.test_accounts[9]
    txn = other_0.transfer(other_1, "1 gwei").transaction

    # Hack in fake sender.
    txn.sender = address
    actual = txn.serialize_transaction()

    # Normally, you'd get a signature error here, but since the account is registered
    # as impersonated, ape lets it slide because it knows it won't match.
    assert isinstance(actual, bytes)


def test_contract_as_sender_non_fork_network(contract_instance):
    expected_err_msg = (
        "Your provider does not support impersonating accounts:\n"
        f"No account with address '{contract_instance}'."
    )
    with pytest.raises(IndexError, match=expected_err_msg):
        contract_instance.setNumber(5, sender=contract_instance)


def test_unlock_with_passphrase_and_sign_message(runner, keyfile_account):
    keyfile_account.unlock(passphrase="a")
    message = encode_defunct(text="Hello Apes!")

    # y: yes, sign (note: unlocking makes the key available but is not the same as autosign).
    with runner.isolation(input="y\n"):
        signature = keyfile_account.sign_message(message)
        assert keyfile_account.check_signature(message, signature)


def test_unlock_from_prompt_and_sign_message(runner, keyfile_account):
    # a = password
    with runner.isolation(input="a\n"):
        keyfile_account.unlock()
        message = encode_defunct(text="Hello Apes!")

    # yes, sign the message
    with runner.isolation(input="y\n"):
        signature = keyfile_account.sign_message(message)
        assert keyfile_account.check_signature(message, signature)


def test_unlock_with_passphrase_and_sign_transaction(runner, keyfile_account, receiver):
    keyfile_account.unlock(passphrase="a")
    # y: yes, sign (note: unlocking makes the key available but is not the same as autosign).
    with runner.isolation(input="y\n"):
        receipt = keyfile_account.transfer(receiver, "1 gwei")
        assert receipt.receiver == receiver


def test_unlock_from_prompt_and_sign_transaction(runner, keyfile_account, receiver):
    # a = password
    with runner.isolation(input="a\n"):
        keyfile_account.unlock()

    # yes, sign the transaction
    with runner.isolation(input="y\n"):
        receipt = keyfile_account.transfer(receiver, "1 gwei")
        assert receipt.receiver == receiver


def test_unlock_with_passphrase_from_env_and_sign_message(runner, keyfile_account):
    ENV_VARIABLE = f"APE_ACCOUNTS_{keyfile_account.alias}_PASSPHRASE"
    # Set environment variable with passphrase
    environ[ENV_VARIABLE] = PASSPHRASE

    # Unlock using environment variable
    keyfile_account.unlock()

    # Account should be unlocked
    assert not keyfile_account.locked

    message = encode_defunct(text="Hello Apes!")

    # y: yes, sign (note: unlocking makes the key available but is not the same as autosign).
    with runner.isolation(input="y\n"):
        signature = keyfile_account.sign_message(message)
        assert keyfile_account.check_signature(message, signature)


def test_unlock_with_wrong_passphrase_from_env(keyfile_account):
    ENV_VARIABLE = f"APE_ACCOUNTS_{keyfile_account.alias}_PASSPHRASE"
    # Set environment variable with passphrase
    environ[ENV_VARIABLE] = INVALID_PASSPHRASE

    # Use pytest.raises to assert that InvalidPasswordError is raised
    with pytest.raises(AccountsError, match="Invalid password"):
        # Unlock using environment variable
        keyfile_account.unlock()

    # Account should be unlocked
    assert keyfile_account.locked


def test_custom_num_of_test_accounts_config(test_accounts, temp_config):
    custom_number_of_test_accounts = 20
    test_config = {
        "test": {
            "number_of_accounts": custom_number_of_test_accounts,
        }
    }

    assert len(test_accounts) == DEFAULT_NUMBER_OF_TEST_ACCOUNTS

    with temp_config(test_config):
        assert len(test_accounts) == custom_number_of_test_accounts


def test_test_accounts_repr(test_accounts):
    actual = repr(test_accounts)
    assert all(a.address in actual for a in test_accounts)


def test_account_comparison_to_non_account(core_account):
    # Before, would get a ConversionError.
    assert core_account != "foo"


def test_create_account(test_accounts):
    length_at_start = len(test_accounts)
    created_acc = test_accounts.generate_test_account()

    assert isinstance(created_acc, TestAccount)
    assert created_acc.index == length_at_start

    second_created_acc = test_accounts.generate_test_account()

    assert created_acc.address != second_created_acc.address
    assert second_created_acc.index == created_acc.index + 1


def test_dir(core_account):
    actual = dir(core_account)
    expected = [
        "address",
        "alias",
        "balance",
        "call",
        "deploy",
        "nonce",
        "prepare_transaction",
        "provider",
        "sign_message",
        "sign_transaction",
        "transfer",
    ]
    assert sorted(actual) == sorted(expected)


def test_is_not_contract(owner, keyfile_account):
    assert not owner.is_contract
    assert not keyfile_account.is_contract


def test_using_different_hd_path(test_accounts, temp_config):
    test_config = {
        "test": {
            "hd_path": "m/44'/60'/0'/0/{}",
        }
    }

    old_first_account = test_accounts[0]
    with temp_config(test_config):
        new_first_account = test_accounts[0]
        assert old_first_account.address != new_first_account.address


def test_using_random_mnemonic(test_accounts, temp_config):
    test_config = {
        "test": {
            "mnemonic": "test_mnemonic_for_ape",
        }
    }

    old_first_account = test_accounts[0]
    with temp_config(test_config):
        new_first_account = test_accounts[0]
        assert old_first_account.address != new_first_account.address


def test_iter_test_accounts(test_accounts):
    actual = list(iter(test_accounts))
    assert len(actual) == len(test_accounts)


def test_declare(contract_container, sender):
    receipt = sender.declare(contract_container)
    assert not receipt.failed


@pytest.mark.parametrize(
    "tx_type,params", [(0, ["gas_price"]), (2, ["max_fee", "max_priority_fee"])]
)
def test_prepare_transaction_using_auto_gas(sender, ethereum, tx_type, params):
    def clear_network_property_cached():
        for field in ("gas_limit", "auto_gas_multiplier"):
            if field in tx.provider.network.__dict__:
                del tx.provider.network.__dict__[field]

    tx = ethereum.create_transaction(type=tx_type, gas_limit="auto")
    auto_gas = AutoGasLimit(multiplier=1.0)
    original_limit = tx.provider.network.config.local.gas_limit

    try:
        tx.provider.network.config.local.gas_limit = auto_gas
        clear_network_property_cached()

        # Show tx doesn't have these by default.
        assert tx.nonce is None
        for param in params:
            # Custom fields depending on type.
            assert getattr(tx, param) is None

        # Gas should NOT yet be estimated, as that happens closer to sending.
        assert tx.gas_limit is None

        # Sets fields.
        tx = sender.prepare_transaction(tx)

        # We expect these fields to have been set.
        assert tx.nonce is not None
        assert tx.gas_limit is not None  # Gas was estimated (using eth_estimateGas).

        # Show multipliers work. First, reset network to use one (hack).
        gas_smaller = tx.gas_limit

        clear_network_property_cached()
        auto_gas.multiplier = 1.1
        tx.provider.network.config.local.gas_limit = auto_gas

        tx2 = ethereum.create_transaction(type=tx_type, gas_limit="auto")
        tx2 = sender.prepare_transaction(tx2)
        gas_bigger = tx2.gas_limit

        assert gas_smaller < gas_bigger

        for param in params:
            assert getattr(tx, param) is not None

    finally:
        tx.provider.network.config.local.gas_limit = original_limit
        clear_network_property_cached()


@pytest.mark.parametrize("type_", (TransactionType.STATIC, TransactionType.DYNAMIC))
def test_prepare_transaction_and_call_using_max_gas(type_, ethereum, sender, eth_tester_provider):
    tx = ethereum.create_transaction(type=type_.value)
    tx = sender.prepare_transaction(tx)
    assert tx.gas_limit == eth_tester_provider.max_gas, "Test setup failed - gas limit unexpected."

    actual = sender.call(tx)
    assert not actual.failed
