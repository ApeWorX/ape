import json

import pytest
from eth_account.messages import encode_defunct

import ape
from ape import convert
from ape.exceptions import AccountsError, ContractLogicError, TransactionError

ALIAS = "__FUNCTIONAL_TESTS_ALIAS__"


@pytest.fixture(autouse=True, scope="module")
def connected(eth_tester_provider):
    yield


@pytest.fixture
def temp_ape_account(keyparams, temp_accounts_path):
    test_keyfile_path = temp_accounts_path / f"{ALIAS}.json"

    if test_keyfile_path.exists():
        # Corrupted from a previous test
        test_keyfile_path.unlink()

    test_keyfile_path.write_text(json.dumps(keyparams))

    yield ape.accounts.load(ALIAS)

    if test_keyfile_path.exists():
        test_keyfile_path.unlink()


def test_sign_message(test_accounts):
    signer = test_accounts[2]
    message = encode_defunct(text="Hello Apes!")
    signature = signer.sign_message(message)
    assert signer.check_signature(message, signature)


def test_transfer(sender, receiver):
    initial_balance = receiver.balance
    sender.transfer(receiver, "1 gwei")
    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected


def test_transfer_using_type_0(sender, receiver):
    initial_balance = receiver.balance
    sender.transfer(receiver, "1 gwei", type=0)
    expected = initial_balance + convert("1 gwei", int)
    assert receiver.balance == expected


def test_deploy(owner, contract_container):
    contract_instance = owner.deploy(contract_container)
    assert contract_instance.address


def test_contract_calls(owner, contract_instance):
    contract_instance.set_number(2, sender=owner)
    assert contract_instance.my_number() == 2


def test_contract_revert(sender, contract_instance):
    # 'sender' is not the owner so it will revert (with a message)
    with pytest.raises(ContractLogicError) as err:
        contract_instance.set_number(5, sender=sender)

    assert str(err.value) == "!authorized"


def test_contract_revert_no_message(owner, contract_instance):
    # The Contract raises empty revert when setting number to 5.
    with pytest.raises(ContractLogicError) as err:
        contract_instance.set_number(5, sender=owner)

    assert str(err.value) == "Transaction failed."  # Default message


def test_send_transaction_with_bad_nonce(sender, receiver):
    # Bump the nonce so we can set one that is too low.
    sender.transfer(receiver, "1 gwei", type=0)

    with pytest.raises(AccountsError) as err:
        sender.transfer(receiver, "1 gwei", type=0, nonce=0)

    assert str(err.value) == "Invalid nonce, will not publish."


def test_send_transaction_without_enough_funds(sender, receiver):
    with pytest.raises(TransactionError) as err:
        sender.transfer(receiver, "10000000000000 ETH")

    assert "Sender does not have enough balance to cover" in str(err.value)


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


def test_autosign(temp_ape_account):
    temp_ape_account.set_autosign(True, passphrase="a")
    message = encode_defunct(text="Hello Apes!")
    signature = temp_ape_account.sign_message(message)
    assert temp_ape_account.check_signature(message, signature)


def test_impersonate_not_implemented(accounts):
    test_address = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
    with pytest.raises(IndexError) as err:
        _ = accounts[test_address]

    expected_err_msg = (
        "Your provider does not support impersonating accounts:\n"
        f"No account with address '{test_address}'."
    )
    assert expected_err_msg in str(err.value)
