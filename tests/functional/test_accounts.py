import pytest
from eip712.messages import EIP712Message
from eth_account.messages import encode_defunct

import ape
from ape import convert
from ape.exceptions import AccountsError, NetworkError, ProjectError, SignatureError
from ape.types.signatures import recover_signer
from ape.utils.testing import DEFAULT_NUMBER_OF_TEST_ACCOUNTS
from ape_ethereum.ecosystem import ProxyType
from ape_test.accounts import TestAccount

MISSING_VALUE_TRANSFER_ERR_MSG = "Must provide 'VALUE' or use 'send_everything=True"

APE_TEST_PATH = "ape_test.accounts.TestAccount"
APE_ACCOUNTS_PATH = "ape_accounts.accounts.KeyfileAccount"


@pytest.fixture
def signer(test_accounts):
    return test_accounts[2]


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


def test_transfer(sender, receiver, eth_tester_provider):
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
    assert sender.balance < 3000000000000  # Part of gas not spent remains
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


def test_transfer_using_type_0(sender, receiver):
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


def test_deploy_and_publish_local_network(owner, contract_container):
    with pytest.raises(ProjectError, match="Can only publish deployments on a live network"):
        owner.deploy(contract_container, 0, publish=True)


def test_deploy_and_publish_live_network_no_explorer(owner, contract_container, dummy_live_network):
    dummy_live_network.__dict__["explorer"] = None
    expected_message = "Unable to publish contract - no explorer plugin installed."
    with pytest.raises(NetworkError, match=expected_message):
        owner.deploy(contract_container, 0, publish=True, required_confirmations=0)


def test_deploy_and_publish(mocker, owner, contract_container, dummy_live_network):
    mock_explorer = mocker.MagicMock()
    dummy_live_network.__dict__["explorer"] = mock_explorer
    contract = owner.deploy(contract_container, 0, publish=True, required_confirmations=0)
    mock_explorer.publish_contract.assert_called_once_with(contract.address)


def test_deploy_and_not_publish(mocker, owner, contract_container, dummy_live_network):
    mock_explorer = mocker.MagicMock()
    dummy_live_network.__dict__["explorer"] = mock_explorer
    owner.deploy(contract_container, 0, publish=True, required_confirmations=0)
    assert not mock_explorer.call_count


def test_deploy_proxy(
    owner, project, vyper_contract_instance, proxy_contract_container, chain, eth_tester_provider
):
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


def test_accounts_address_access(test_accounts, accounts):
    assert accounts[test_accounts[0].address] == test_accounts[0]


def test_accounts_contains(accounts, test_accounts):
    assert test_accounts[0].address in accounts


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


def test_impersonate_not_implemented(accounts):
    test_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    expected_err_msg = (
        "Your provider does not support impersonating accounts:\n"
        f"No account with address '{test_address}'."
    )
    with pytest.raises(IndexError, match=expected_err_msg):
        _ = accounts[test_address]


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
    created_acc = test_accounts.generate_test_account()

    assert isinstance(created_acc, TestAccount)
    assert created_acc.index == len(test_accounts)

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
