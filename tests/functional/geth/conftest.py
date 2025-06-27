import copy
from pathlib import Path

import pytest

from ape_node.provider import Node
from tests.functional.data.python import TRACE_RESPONSE


@pytest.fixture
def parity_trace_response():
    return TRACE_RESPONSE


@pytest.fixture
def contract_with_call_depth_geth(
    owner, geth_provider, project, leaf_contract_geth, middle_contract_geth
):
    """
    This contract has methods that make calls to other local contracts
    and is used for any testing that requires nested calls, such as
    call trees or event-name clashes.
    """
    return owner.deploy(project.ContractA, middle_contract_geth, leaf_contract_geth)


@pytest.fixture
def error_contract_geth(owner, project, geth_provider):
    _ = geth_provider  # Ensure uses geth
    return owner.deploy(project.HasError, 1)


@pytest.fixture
def leaf_contract_geth(project, geth_provider, owner):
    """
    The last contract called by `contract_with_call_depth`.
    """
    return owner.deploy(project.ContractC)


@pytest.fixture
def middle_contract_geth(project, geth_provider, owner, leaf_contract_geth):
    """
    The middle contract called by `contract_with_call_depth`.
    """
    return owner.deploy(project.ContractB, leaf_contract_geth)


@pytest.fixture
def mock_geth(geth_provider, mock_web3):
    provider = Node(
        name="node",
        network=geth_provider.network,
        provider_settings={},
        data_folder=Path(),
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
    project,
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
    with project.temp_config(**config):
        geth_provider.network = ethereum.apenet
        try:
            with networks.ethereum.apenet.use_provider("node"):
                yield

        finally:
            geth_provider.network = actual
