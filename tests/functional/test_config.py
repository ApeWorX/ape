import logging

import pytest

from ape.managers.config import DeploymentConfigCollection

DEPLOYMENTS = {
    "ethereum": {
        "mainnet": [
            {"address": 0x0C25212C557D00024B7CA3DF3238683A35541354, "contract_type": "MyContract"}
        ]
    }
}


def test_integer_deployment_addresses():
    config = DeploymentConfigCollection(DEPLOYMENTS, ["ethereum"], ["mainnet"])
    assert (
        config["ethereum"]["mainnet"][0]["address"] == "0x0c25212c557d00024b7Ca3df3238683A35541354"
    )


@pytest.mark.parametrize(
    "ecosystems,networks,err_part",
    [(["fantom"], ["mainnet"], "ecosystem"), (["ethereum"], ["local"], "network")],
)
def test_bad_value_in_deployments(ecosystems, networks, err_part, caplog):
    with caplog.at_level(logging.WARNING):
        DeploymentConfigCollection(DEPLOYMENTS, ecosystems, networks)
        assert "Invalid ecosystem 'ethereum' in deployments config." in caplog.records[0].message
