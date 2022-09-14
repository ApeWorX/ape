import pytest

from ape import Contract
from ape.exceptions import NetworkError, ProjectError
from ape_ethereum.ecosystem import ProxyType


def test_deploy(
    sender, contract_container, networks_connected_to_tester, project, chain, clean_contracts_cache
):
    contract = contract_container.deploy(sender=sender, something_else="IGNORED")
    assert contract.txn_hash

    # Verify can reload same contract from cache
    contract_from_cache = Contract(contract.address)
    assert contract_from_cache.contract_type == contract.contract_type
    assert contract_from_cache.address == contract.address
    assert contract_from_cache.txn_hash == contract.txn_hash


def test_deploy_and_publish_local_network(owner, contract_container):
    with pytest.raises(ProjectError, match="Can only publish deployments on a live network"):
        contract_container.deploy(sender=owner, publish=True)


def test_deploy_and_publish_live_network_no_explorer(
    owner, project, contract_container, dummy_live_network
):
    _ = project  # Ensure active project for `track_deployment` to work
    dummy_live_network.__dict__["explorer"] = None
    expected_message = "Unable to publish contract - no explorer plugin installed."
    with pytest.raises(NetworkError, match=expected_message):
        contract_container.deploy(sender=owner, publish=True, required_confirmations=0)


def test_deploy_and_publish(mocker, owner, contract_container, dummy_live_network):
    mock_explorer = mocker.MagicMock()
    dummy_live_network.__dict__["explorer"] = mock_explorer
    contract = contract_container.deploy(sender=owner, publish=True, required_confirmations=0)
    mock_explorer.publish_contract.assert_called_once_with(contract.address)


def test_deploy_and_not_publish(mocker, owner, contract_container, dummy_live_network):
    mock_explorer = mocker.MagicMock()
    dummy_live_network.__dict__["explorer"] = mock_explorer
    contract_container.deploy(sender=owner, publish=False, required_confirmations=0)
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
    instance = proxy_contract_container.deploy(target, sender=owner)
    assert instance.address not in chain.contracts._local_contract_types
    assert instance.address in chain.contracts._local_proxies

    actual = chain.contracts._local_proxies[instance.address]
    assert actual.target == target
    assert actual.type == ProxyType.Delegate
