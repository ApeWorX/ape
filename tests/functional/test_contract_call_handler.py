import pytest
from eth_pydantic_types import HexBytes

from ape.contracts.base import ContractCallHandler
from ape.exceptions import ContractNotFoundError
from ape.utils import ZERO_ADDRESS
from ape_test.provider import LocalProvider


def test_struct_input(
    call_handler_with_struct_input, struct_input_for_call, output_from_struct_input_call
):
    actual = call_handler_with_struct_input.encode_input(*struct_input_for_call)
    assert actual == output_from_struct_input_call


def test_call_contract_not_found(mocker, method_abi_with_struct_input, networks):
    (networks.ethereum.local.__dict__ or {}).pop("explorer", None)
    contract = mocker.MagicMock()
    contract.address = ZERO_ADDRESS
    contract.is_contract = False
    method = method_abi_with_struct_input
    handler = ContractCallHandler(contract=contract, abis=[method])
    expected = f"Failed to get contract type for address '{ZERO_ADDRESS}'."
    with pytest.raises(ContractNotFoundError, match=expected):
        handler()


def test_transact_contract_not_found(mocker, owner, method_abi_with_struct_input, networks):
    (networks.ethereum.local.__dict__ or {}).pop("explorer", None)
    contract = mocker.MagicMock()
    contract.address = ZERO_ADDRESS
    contract.is_contract = False
    method = method_abi_with_struct_input
    handler = ContractCallHandler(contract=contract, abis=[method])
    expected = rf"Failed to get contract type for address '{ZERO_ADDRESS}'\."
    with pytest.raises(ContractNotFoundError, match=expected):
        handler.transact(sender=owner)


def test_call_precompile_with_explicit_contract_type(mocker, eth_tester_provider, project):
    # ApeWorX/ape#2705: precompiles have no on-chain bytecode, yet are callable
    # when the user explicitly provides the contract type via `.at()`.
    precompile_address = "0x0000000000000000000000000000000000000807"
    contract = project.VyperContract.at(precompile_address)
    assert contract.explicit_contract_type is True

    # eth-tester has no precompile at this address, so simulate its returndata.
    returndata = HexBytes(b"\x00" * 31 + b"\x2a")
    mocker.patch.object(LocalProvider, "send_call", return_value=returndata)
    assert contract.myNumber() == 42


def test_transact_precompile_with_explicit_contract_type(project, owner):
    # ApeWorX/ape#2705: sending a transaction to a precompile address must not
    # be blocked by the no-code check when the type was explicitly provided.
    precompile_address = "0x0000000000000000000000000000000000000807"
    contract = project.VyperContract.at(precompile_address)
    assert contract.explicit_contract_type is True

    receipt = contract.setNumber(3, sender=owner)
    assert receipt.txn_hash
