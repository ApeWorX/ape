from typing import Dict

import pytest

from ape.exceptions import ConfigError
from ape.managers.config import DeploymentConfigCollection


def test_integer_deployment_addresses(networks):
    deployments_data = _create_deployments()
    config = DeploymentConfigCollection(deployments_data, networks)
    assert config["ethereum"]["local"][0]["address"] == "0x0c25212c557d00024b7Ca3df3238683A35541354"


def test_bad_ecosystem_in_deployments(networks):
    deployments = _create_deployments(ecosystem_name="FAKE-ECOSYSTEM")
    with pytest.raises(ConfigError) as err:
        DeploymentConfigCollection(deployments, networks)

    assert "Invalid ecosystem" in str(err.value)


def test_bad_network_in_deployments(networks):
    deployments = _create_deployments(network_name="FAKE-NETWORK")
    with pytest.raises(ConfigError) as err:
        DeploymentConfigCollection(deployments, networks)

    assert "Invalid network" in str(err.value)


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
