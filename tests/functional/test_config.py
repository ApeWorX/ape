import logging
from typing import Dict

import pytest

from ape.api import PluginConfig
from ape.exceptions import NetworkError
from ape.managers.config import DeploymentConfigCollection
from ape_ethereum.ecosystem import NetworkConfig
from tests.functional.conftest import PROJECT_WITH_LONG_CONTRACTS_FOLDER


def test_integer_deployment_addresses(networks):
    deployments_data = _create_deployments()
    config = DeploymentConfigCollection(
        deployments_data, {"ethereum": networks.ethereum}, ["local"]
    )
    assert config["ethereum"]["local"][0]["address"] == "0x0c25212c557d00024b7Ca3df3238683A35541354"


@pytest.mark.parametrize(
    "ecosystems,networks,err_part",
    [(["ERRORS"], ["mainnet"], "ecosystem"), (["ethereum"], ["ERRORS"], "network")],
)
def test_bad_value_in_deployments(ecosystems, networks, err_part, caplog, plugin_manager):
    deployments = _create_deployments()
    with caplog.at_level(logging.WARNING):
        all_ecosystems = dict(plugin_manager.ecosystems)
        ecosystem_dict = {e: all_ecosystems[e] for e in ecosystems if e in all_ecosystems}
        DeploymentConfigCollection(deployments, ecosystem_dict, networks)
        assert len(caplog.records) > 0, "Nothing was logged"
        assert f"Invalid {err_part}" in caplog.records[0].message


def _create_deployments(ecosystem_name: str = "ethereum", network_name: str = "local") -> Dict:
    return {
        ecosystem_name: {
            network_name: [
                {
                    "address": 0x0C25212C557D00024B7CA3DF3238683A35541354,
                    "contract_type": "MyContract",
                }
            ]
        }
    }


def test_ethereum_network_configs(config, temp_config):
    eth_config = {"ethereum": {"rinkeby": {"default_provider": "test"}}}
    with temp_config(eth_config):
        actual = config.get_config("ethereum")
        assert actual.rinkeby.default_provider == "test"

        # Ensure that non-updated fields remain unaffected
        assert actual.rinkeby.block_time == 15


def test_default_provider_not_found(temp_config, networks):
    provider_name = "DOES_NOT_EXIST"
    network_name = "local"
    eth_config = {"ethereum": {network_name: {"default_provider": provider_name}}}

    with temp_config(eth_config):
        with pytest.raises(
            NetworkError, match=f"Provider '{provider_name}' not found in network '{network_name}'."
        ):
            # Trigger re-loading the Ethereum config.
            _ = networks.ecosystems


def test_dependencies(dependency_config, config):
    assert len(config.dependencies) == 1
    assert config.dependencies[0].name == "testdependency"
    assert config.dependencies[0].contracts_folder == "source/v0.1"
    assert config.dependencies[0].local == str(PROJECT_WITH_LONG_CONTRACTS_FOLDER)


def test_config_access():
    config = NetworkConfig()
    assert "default_provider" in config
    assert (
        config.default_provider
        == config["default_provider"]
        == getattr(config, "default-provider")
        == "geth"
    )


def test_plugin_config_updates_when_default_is_empty_dict():
    class SubConfig(PluginConfig):
        foo: int = 0
        bar: int = 1

    class MyConfig(PluginConfig):
        sub: Dict[str, Dict[str, SubConfig]] = {}

    overrides = {"sub": {"baz": {"test": {"foo": 5}}}}
    actual = MyConfig.from_overrides(overrides)
    assert actual.sub == {"baz": {"test": SubConfig(foo=5, bar=1)}}
