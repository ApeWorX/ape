import pytest

from ape import Contract
from ape.exceptions import NetworkError, ProjectError


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


def test_deploy_and_publish_live_network_no_explorer(owner, contract_container, dummy_live_network):
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
    initial_deployed_contract = owner.deploy(project_with_contract.ApeContract0)
    actual = project_with_contract.ApeContract0.deployments[-1].address
    expected = initial_deployed_contract.address
    assert actual == expected
