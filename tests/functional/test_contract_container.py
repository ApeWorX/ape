import pytest
from ethpm_types import ContractType

from ape import Contract
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import (
    ArgumentsLengthError,
    MissingDeploymentBytecodeError,
    NetworkError,
    ProjectError,
)
from ape_ethereum.ecosystem import ProxyType


def test_deploy(
    not_owner,
    contract_container,
    networks_connected_to_tester,
    project,
    chain,
    clean_contracts_cache,
):
    contract = contract_container.deploy(4, sender=not_owner, something_else="IGNORED")
    assert contract.txn_hash
    assert contract.myNumber() == 4

    # Verify can reload same contract from cache
    contract_from_cache = Contract(contract.address)
    assert contract_from_cache.contract_type == contract.contract_type
    assert contract_from_cache.address == contract.address
    assert contract_from_cache.txn_hash == contract.txn_hash


def test_deploy_wrong_number_of_arguments(
    not_owner,
    contract_container,
    networks_connected_to_tester,
    project,
    chain,
    clean_contracts_cache,
):
    expected = (
        r"The number of the given arguments \(0\) do not match what is defined in the "
        r"ABI:\n\n\t.*__init__\(uint256 num\).*"
    )
    with pytest.raises(ArgumentsLengthError, match=expected):
        contract_container.deploy(sender=not_owner)


def test_deploy_and_publish_local_network(owner, contract_container):
    with pytest.raises(ProjectError, match="Can only publish deployments on a live network"):
        contract_container.deploy(0, sender=owner, publish=True)


def test_deploy_and_publish_live_network_no_explorer(owner, contract_container, dummy_live_network):
    dummy_live_network.__dict__["explorer"] = None
    expected_message = "Unable to publish contract - no explorer plugin installed."
    with pytest.raises(NetworkError, match=expected_message):
        contract_container.deploy(0, sender=owner, publish=True, required_confirmations=0)


def test_deploy_and_publish(owner, contract_container, dummy_live_network, mock_explorer):
    dummy_live_network.__dict__["explorer"] = mock_explorer
    contract = contract_container.deploy(0, sender=owner, publish=True, required_confirmations=0)
    mock_explorer.publish_contract.assert_called_once_with(contract.address)


def test_deploy_and_not_publish(owner, contract_container, dummy_live_network, mock_explorer):
    dummy_live_network.__dict__["explorer"] = mock_explorer
    contract_container.deploy(0, sender=owner, publish=False, required_confirmations=0)
    assert not mock_explorer.call_count


def test_deploy_privately(owner, contract_container):
    deploy_0 = owner.deploy(contract_container, 3, private=True)
    assert isinstance(deploy_0, ContractInstance)

    deploy_1 = contract_container.deploy(3, sender=owner, private=True)
    assert isinstance(deploy_1, ContractInstance)


@pytest.mark.parametrize("bytecode", (None, {}, {"bytecode": "0x"}))
def test_deploy_no_deployment_bytecode(owner, bytecode):
    """
    https://github.com/ApeWorX/ape/issues/1904
    """
    expected = (
        r"Cannot deploy: contract 'Apes' has no deployment-bytecode\. "
        r"Are you attempting to deploy an interface\?"
    )
    contract_type = ContractType.model_validate(
        {"abi": [], "contractName": "Apes", "deploymentBytecode": bytecode}
    )
    contract = ContractContainer(contract_type)
    with pytest.raises(MissingDeploymentBytecodeError, match=expected):
        contract.deploy(sender=owner)


def test_deployments(owner, eth_tester_provider, vyper_contract_container):
    initial_deployed_contract = vyper_contract_container.deploy(10000000, sender=owner)
    actual = vyper_contract_container.deployments[-1].address
    expected = initial_deployed_contract.address
    assert actual == expected


def test_deploy_proxy(
    owner, project, vyper_contract_instance, proxy_contract_container, chain, eth_tester_provider
):
    target = vyper_contract_instance.address
    proxy = proxy_contract_container.deploy(target, sender=owner)
    assert proxy.address in chain.contracts._local_contract_types
    assert proxy.address in chain.contracts._local_proxies

    actual = chain.contracts._local_proxies[proxy.address]
    assert actual.target == target
    assert actual.type == ProxyType.Delegate

    # Show we get the implementation contract type using the proxy address
    implementation = chain.contracts.instance_at(proxy.address)
    assert implementation.contract_type == vyper_contract_instance.contract_type


def test_source_path_in_project(project_with_contract):
    contract = project_with_contract.contracts["Contract"]
    contract_container = project_with_contract.get_contract("Contract")
    expected = project_with_contract.path / contract.source_id
    assert contract_container.source_path.is_file()
    assert contract_container.source_path == expected


def test_source_path_out_of_project(contract_container, project_with_contract):
    assert not contract_container.source_path


def test_encode_constructor_input(contract_container, calldata):
    constructor = contract_container.constructor
    actual = constructor.encode_input(222)
    expected = calldata[4:]  # Strip off setNumber() method ID
    assert actual == expected


def test_decode_constructor_input(contract_container, calldata):
    constructor = contract_container.constructor
    constructor_calldata = calldata[4:]  # Strip off setNumber() method ID
    actual = constructor.decode_input(constructor_calldata)
    expected = "constructor(uint256)", {"num": 222}
    assert actual == expected


def test_decode_input(contract_container, calldata):
    actual = contract_container.decode_input(calldata)
    expected = "setNumber(uint256)", {"num": 222}
    assert actual == expected


def test_declare(contract_container, sender):
    receipt = contract_container.declare(sender=sender)
    assert not receipt.failed


def test_source_id(contract_container):
    actual = contract_container.source_id
    expected = contract_container.contract_type.source_id
    # Is just a pass-through (via extras-model), but making sure it works.
    assert actual == expected
