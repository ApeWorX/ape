import pytest

from ape import Contract
from ape.exceptions import NetworkError, ProjectError
from ape_ethereum.ecosystem import ProxyType


def test_deploy(
    sender, contract_container, networks_connected_to_tester, project, chain, clean_contracts_cache
):
    contract = contract_container.deploy(4, sender=sender, something_else="IGNORED")
    assert contract.txn_hash
    assert contract.myNumber() == 4

    # Verify can reload same contract from cache
    contract_from_cache = Contract(contract.address)
    assert contract_from_cache.contract_type == contract.contract_type
    assert contract_from_cache.address == contract.address
    assert contract_from_cache.txn_hash == contract.txn_hash


def test_deploy_and_publish_local_network(owner, contract_container):
    with pytest.raises(ProjectError, match="Can only publish deployments on a live network"):
        contract_container.deploy(0, sender=owner, publish=True)


def test_deploy_and_publish_live_network_no_explorer(owner, contract_container, dummy_live_network):
    dummy_live_network.__dict__["explorer"] = None
    expected_message = "Unable to publish contract - no explorer plugin installed."
    with pytest.raises(NetworkError, match=expected_message):
        contract_container.deploy(0, sender=owner, publish=True, required_confirmations=0)


def test_deploy_and_publish(mocker, owner, contract_container, dummy_live_network):
    mock_explorer = mocker.MagicMock()
    dummy_live_network.__dict__["explorer"] = mock_explorer
    contract = contract_container.deploy(0, sender=owner, publish=True, required_confirmations=0)
    mock_explorer.publish_contract.assert_called_once_with(contract.address)


def test_deploy_and_not_publish(mocker, owner, contract_container, dummy_live_network):
    mock_explorer = mocker.MagicMock()
    dummy_live_network.__dict__["explorer"] = mock_explorer
    contract_container.deploy(0, sender=owner, publish=False, required_confirmations=0)
    assert not mock_explorer.call_count


def test_deployment_property(chain, owner, project_with_contract, eth_tester_provider):
    initial_deployed_contract = project_with_contract.ApeContract0.deploy(sender=owner)
    actual = project_with_contract.ApeContract0.deployments[-1].address
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
    contracts_folder = project_with_contract.contracts_folder
    contract = project_with_contract.contracts["Contract"]
    path = contracts_folder / contract.source_id
    assert path.is_file()
    assert project_with_contract.get_contract("Contract").source_path == path


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
