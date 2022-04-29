import logging
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Dict

import pytest
import yaml

from ape.exceptions import NetworkError
from ape.managers.config import CONFIG_FILE_NAME, DeploymentConfigCollection


@contextmanager
def temp_config(data: Dict, config):
    with tempfile.TemporaryDirectory() as temp_dir_str:
        temp_dir = Path(temp_dir_str)
        with config.using_project(temp_dir):
            config._cached_configs = {}
            config_file = temp_dir / CONFIG_FILE_NAME
            config_file.touch()
            config_file.write_text(yaml.dump(data))
            yield
            config_file.unlink()
            config._cached_configs = {}


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


def test_default_provider_not_found(config, networks):
    eth_config = {"ethereum": {"mainnet": {"default_provider": "DOES_NOT_EXIST"}}}

    with temp_config(eth_config, config):
        with pytest.raises(NetworkError, match="Provider 'DOES_NOT_EXIST' not found."):
            # Trigger re-loading the Ethereum config.
            _ = networks.ecosystems
