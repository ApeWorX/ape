import pytest

from ape.contracts.base import ContractCallHandler
from ape.exceptions import ContractNotDeployedError, ContractNotFoundError
from ape.utils import ZERO_ADDRESS


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
    expected = rf"No contract code at address '{ZERO_ADDRESS}' on network 'ethereum:local:test'\.$"
    with pytest.raises(ContractNotDeployedError, match=expected):
        handler()


def test_transact_contract_not_found(mocker, owner, method_abi_with_struct_input, networks):
    (networks.ethereum.local.__dict__ or {}).pop("explorer", None)
    contract = mocker.MagicMock()
    contract.address = ZERO_ADDRESS
    contract.is_contract = False
    method = method_abi_with_struct_input
    handler = ContractCallHandler(contract=contract, abis=[method])
    expected = rf"No contract code at address '{ZERO_ADDRESS}'"
    with pytest.raises(ContractNotDeployedError, match=expected):
        handler.transact(sender=owner)


def test_call_contract_not_deployed_is_contract_not_found(
    mocker, method_abi_with_struct_input, networks
):
    """
    Code catching the broader ``ContractNotFoundError`` still catches this case.
    """
    contract = mocker.MagicMock()
    contract.address = ZERO_ADDRESS
    contract.is_contract = False
    handler = ContractCallHandler(contract=contract, abis=[method_abi_with_struct_input])
    with pytest.raises(ContractNotFoundError):
        handler()
