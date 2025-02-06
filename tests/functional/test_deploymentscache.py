import json

import pytest

from ape.managers._deploymentscache import DeploymentDiskCache


class TestDeploymentDiskCache:
    CONTRACT_NAME = "DeploymentTestContractName"

    @pytest.fixture(scope="class")
    def contract_name(self):
        return self.CONTRACT_NAME

    @pytest.fixture
    def cache(self):
        return DeploymentDiskCache()

    def test_cache_deployment(self, zero_address, cache, contract_name):
        cache.cache_deployment(zero_address, contract_name)
        assert contract_name in cache
        assert cache[contract_name][-1].address == zero_address

    def test_cache_deployment_live_network(
        self, zero_address, cache, contract_name, mock_sepolia, eth_tester_provider
    ):
        local = eth_tester_provider.network
        ecosystem_name = mock_sepolia.ecosystem.name

        eth_tester_provider.network = mock_sepolia
        cache.cache_deployment(zero_address, contract_name)
        eth_tester_provider.network = local

        assert contract_name in cache
        assert cache[contract_name][-1].address == zero_address
        # Show it is also cached on disk.
        disk_data = json.loads(cache.cachefile.read_text())
        assert (
            disk_data["ecosystems"][ecosystem_name][mock_sepolia.name][contract_name][0]["address"]
            == zero_address
        )

    def test_cache_deployment_live_network_new_ecosystem(
        self, zero_address, cache, contract_name, mock_sepolia, eth_tester_provider
    ):
        """
        Tests the case when caching a deployment in a new ecosystem.
        """
        ecosystem_name = mock_sepolia.ecosystem.name
        local = eth_tester_provider.network
        eth_tester_provider.network = mock_sepolia
        # Make the ecosystem key not exist.
        deployments = cache._deployments.pop(ecosystem_name, None)
        cache.cache_deployment(zero_address, contract_name)
        eth_tester_provider.network = local
        if deployments is not None:
            cache._deployments[ecosystem_name] = deployments
        cache.cachefile.unlink(missing_ok=True)

        # In memory cached still work.
        assert contract_name in cache
        assert cache[contract_name][-1].address == zero_address

        # Show it did NOT cache to disk.
        if cache.cachefile.is_file():
            disk_data = json.loads(cache.cachefile.read_text())
            assert contract_name not in disk_data["ecosystems"][ecosystem_name]["sepolia"]
