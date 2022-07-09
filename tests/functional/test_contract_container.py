from ape import Contract

from .conftest import SOLIDITY_CONTRACT_ADDRESS, VYPER_CONTRACT_ADDRESS


def test_deploy(
    sender, contract_container, networks_connected_to_tester, project, chain, clean_contracts_cache
):
    contract = contract_container.deploy(sender=sender, something_else="IGNORED")
    assert contract.address in (SOLIDITY_CONTRACT_ADDRESS, VYPER_CONTRACT_ADDRESS)

    # Verify can reload same contract from cache
    contract_from_cache = Contract(contract.address)
    assert contract_from_cache.contract_type == contract.contract_type
    assert contract_from_cache.address == contract.address

    # Clean up for next test
    del chain.contracts._local_contracts[contract_from_cache.address]


def test_deployment_property(chain, owner, project_with_contract, eth_tester_provider):
    initial_deployed_contract = owner.deploy(project_with_contract.ApeContract0)
    actual = project_with_contract.ApeContract0.deployments[-1].address
    expected = initial_deployed_contract.address
    assert actual == expected
