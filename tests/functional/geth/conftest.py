import copy
from pathlib import Path

import pytest

from ape.contracts import ContractContainer
from ape_geth.provider import Geth
from tests.functional.data.python import TRACE_RESPONSE


@pytest.fixture
def txn_hash():
    return "0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d"


@pytest.fixture
def parity_trace_response():
    return TRACE_RESPONSE


@pytest.fixture
def geth_contract(geth_account, vyper_contract_container, geth_provider):
    return geth_account.deploy(vyper_contract_container, 0)


@pytest.fixture
def contract_with_call_depth_geth(
    owner, geth_provider, get_contract_type, leaf_contract_geth, middle_contract_geth
):
    """
    This contract has methods that make calls to other local contracts
    and is used for any testing that requires nested calls, such as
    call trees or event-name clashes.
    """
    contract = ContractContainer(get_contract_type("ContractA"))
    return owner.deploy(contract, middle_contract_geth, leaf_contract_geth)


@pytest.fixture
def error_contract_geth(owner, error_contract_container, geth_provider):
    _ = geth_provider  # Ensure uses geth
    return owner.deploy(error_contract_container, 1)


@pytest.fixture
def leaf_contract_geth(geth_provider, owner, get_contract_type):
    """
    The last contract called by `contract_with_call_depth`.
    """
    ct = get_contract_type("ContractC")
    return owner.deploy(ContractContainer(ct))


@pytest.fixture
def middle_contract_geth(geth_provider, owner, leaf_contract_geth, get_contract_type):
    """
    The middle contract called by `contract_with_call_depth`.
    """
    ct = get_contract_type("ContractB")
    return owner.deploy(ContractContainer(ct), leaf_contract_geth)


@pytest.fixture
def mock_geth(geth_provider, mock_web3):
    provider = Geth(
        name="geth",
        network=geth_provider.network,
        provider_settings={},
        data_folder=Path("."),
        request_header={},
    )
    original_web3 = provider._web3
    provider._web3 = mock_web3
    yield provider
    provider._web3 = original_web3


@pytest.fixture
def geth_receipt(contract_with_call_depth_geth, owner, geth_provider):
    return contract_with_call_depth_geth.methodWithoutArguments(sender=owner)


@pytest.fixture
def geth_vyper_receipt(geth_vyper_contract, owner):
    return geth_vyper_contract.setNumber(44, sender=owner)


@pytest.fixture
def custom_network_connection(
    geth_provider,
    ethereum,
    temp_config,
    custom_network_name_0,
    custom_networks_config_dict,
    networks,
):
    data = copy.deepcopy(custom_networks_config_dict)
    data["networks"]["custom"][0]["chain_id"] = geth_provider.chain_id
    config = {
        ethereum.name: {custom_network_name_0: {"default_transaction_type": 0}},
        geth_provider.name: {ethereum.name: {custom_network_name_0: {"uri": geth_provider.uri}}},
        **data,
    }
    actual = geth_provider.network
    with temp_config(config):
        geth_provider.network = ethereum.apenet
        try:
            with networks.ethereum.apenet.use_provider("geth"):
                yield

        finally:
            geth_provider.network = actual
