from pathlib import Path
from typing import Optional, Union

import pytest
from pydantic_settings import SettingsConfigDict

from ape.api.config import ApeConfig, ConfigEnum, PluginConfig
from ape.exceptions import ConfigError
from ape.managers.config import CONFIG_FILE_NAME, merge_configs
from ape.types import GasLimit
from ape_ethereum.ecosystem import NetworkConfig
from ape_networks import CustomNetwork
from tests.functional.conftest import PROJECT_WITH_LONG_CONTRACTS_FOLDER


def test_model_validate_empty():
    data: dict = {}
    cfg = ApeConfig.model_validate(data)
    assert cfg.contracts_folder is None


def test_model_validate():
    data = {"contracts_folder": "src"}
    cfg = ApeConfig.model_validate(data)
    assert cfg.contracts_folder == "src"


def test_model_validate_none_contracts_folder():
    data = {"contracts_folder": None}
    cfg = ApeConfig.model_validate(data)
    assert cfg.contracts_folder is None


def test_model_validate_path_contracts_folder():
    path = Path.home() / "contracts"
    data = {"contracts_folder": path}
    cfg = ApeConfig.model_validate(data)
    assert cfg.contracts_folder == str(path)


def test_deployments(networks_connected_to_tester, owner, vyper_contract_container, project):
    _ = networks_connected_to_tester  # Connection needs to lookup config.

    # First, obtain a "previously-deployed" contract.
    instance = vyper_contract_container.deploy(1000200000, sender=owner)
    address = instance.address

    # Create a config using this new contract for a "later time".
    deploys = {
        **_create_deployments(address=address, contract_name=instance.contract_type.name),
    }
    with project.temp_config(**{"deployments": deploys}):
        deploy_config = project.config.deployments
        assert deploy_config["ethereum"]["local"][0]["address"] == address
        deployment = vyper_contract_container.deployments[0]

    assert deployment.address == instance.address


def test_deployments_integer_type_addresses(networks, project):
    deploys = {
        **_create_deployments(address=0x0C25212C557D00024B7CA3DF3238683A35541354),
    }
    with project.temp_config(**{"deployments": deploys}):
        deploy_config = project.config.deployments
        assert (
            deploy_config["ethereum"]["local"][0]["address"]
            == "0x0c25212c557d00024b7Ca3df3238683A35541354"
        )


def test_deployments_bad_ecosystem(project):
    deployments = _create_deployments(ecosystem_name="madeup")
    with project.temp_config(deployments=deployments):
        with pytest.raises(
            ConfigError, match=r"Invalid ecosystem 'madeup' in deployments config\."
        ):
            _ = project.config.deployments


def test_deployments_bad_network(project):
    deployments = _create_deployments(network_name="madeup")
    with project.temp_config(deployments=deployments):
        with pytest.raises(
            ConfigError, match=r"Invalid network 'ethereum:madeup' in deployments config\."
        ):
            _ = project.config.deployments


def _create_deployments(
    ecosystem_name: str = "ethereum",
    network_name: str = "local",
    address: Union[int, str] = "0x0C25212C557D00024B7CA3DF3238683A35541354",
    contract_name: Optional[str] = "MyContract",
) -> dict:
    return {
        ecosystem_name: {
            network_name: [
                {
                    "address": address,
                    "contract_type": contract_name,
                }
            ]
        }
    }


def test_ethereum_network_configs(config, project):
    eth_config = {"ethereum": {"sepolia": {"default_provider": "test"}}}
    with project.temp_config(**eth_config):
        actual = config.get_config("ethereum")
        assert actual.sepolia.default_provider == "test"

        # Ensure that non-updated fields remain unaffected
        assert actual.sepolia.block_time == 15


def test_network_gas_limit_default(config):
    eth_config = config.get_config("ethereum")

    assert eth_config.sepolia.gas_limit == "auto"
    assert eth_config.local.gas_limit == "max"


def _sepolia_with_gas_limit(gas_limit: GasLimit) -> dict:
    return {
        "ethereum": {
            "sepolia": {
                "default_provider": "test",
                "gas_limit": gas_limit,
            }
        }
    }


@pytest.mark.parametrize("gas_limit", ("auto", "max"))
def test_network_gas_limit_string_config(gas_limit, project):
    eth_config = _sepolia_with_gas_limit(gas_limit)

    with project.temp_config(**eth_config):
        actual = project.config.get_config("ethereum")

        assert actual.sepolia.gas_limit == gas_limit

        # Local configuration is unaffected
        assert actual.local.gas_limit == "max"


@pytest.mark.parametrize("gas_limit", (1234, "1234", 0x4D2, "0x4D2"))
def test_network_gas_limit_numeric_config(gas_limit, project):
    eth_config = _sepolia_with_gas_limit(gas_limit)
    with project.temp_config(**eth_config):
        actual = project.config.get_config("ethereum")
        assert actual.sepolia.gas_limit == 1234

        # Local configuration is unaffected
        assert actual.local.gas_limit == "max"


def test_network_gas_limit_invalid_numeric_string(project):
    """
    Test that using hex strings for a network's gas_limit config must be
    prefixed with '0x'
    """
    eth_config = _sepolia_with_gas_limit("4D2")
    with project.temp_config(**eth_config):
        with pytest.raises(AttributeError, match="Gas limit hex str must include '0x' prefix."):
            _ = project.config.ethereum


def test_dependencies(project_with_dependency_config):
    config = project_with_dependency_config.config
    assert len(config.dependencies) == 1
    assert config.dependencies[0]["name"] == "testdependency"
    assert config.dependencies[0]["config_override"]["contracts_folder"] == "source/v0.1"
    assert config.dependencies[0]["local"] == str(PROJECT_WITH_LONG_CONTRACTS_FOLDER)


def test_config_access():
    config = NetworkConfig()
    assert "default_provider" in config
    assert (
        config.default_provider
        == config["default_provider"]
        == getattr(config, "default-provider")
        == "node"
    )


def test_plugin_config_updates_when_default_is_empty_dict():
    class SubConfig(PluginConfig):
        foo: int = 0
        bar: int = 1

    class MyConfig(PluginConfig):
        sub: dict[str, dict[str, SubConfig]] = {}

    overrides = {"sub": {"baz": {"test": {"foo": 5}}}}
    actual = MyConfig.from_overrides(overrides)
    assert actual.sub == {"baz": {"test": SubConfig(foo=5, bar=1)}}


@pytest.mark.parametrize("override_0,override_1", [(True, {"foo": 0}), ({"foo": 0}, True)])
def test_plugin_config_with_union_dicts(override_0, override_1):
    class SubConfig(PluginConfig):
        bool_or_dict: Union[bool, dict] = True
        dict_or_bool: Union[dict, bool] = {}

    config = SubConfig.from_overrides({"bool_or_dict": override_0, "dict_or_bool": override_1})
    assert config.bool_or_dict == override_0
    assert config.dict_or_bool == override_1


def test_global_config(data_folder, config):
    config_file = data_folder / CONFIG_FILE_NAME
    config_file.unlink(missing_ok=True)
    config_file.touch()
    config_content = """
test:
  number_of_accounts: 11
""".strip()
    config_file.write_text(config_content)
    global_config = config.load_global_config()
    assert global_config.get_config("test").number_of_accounts == 11
    config_file.unlink(missing_ok=True)


def test_merge_configs():
    """
    The test covers most cases in `merge_config()`. See comment below explaining
    `expected`.
    """
    global_config = {
        "ethereum": {
            "mainnet": {"default_provider": "node"},
            "local": {"default_provider": "test", "required_confirmations": 5},
        }
    }
    project_config = {
        "ethereum": {
            "local": {"default_provider": "node"},
            "sepolia": {"default_provider": "alchemy"},
        },
        "test": "foo",
    }
    actual = merge_configs(global_config, project_config)

    # Expected case `key only in global`: "mainnet"
    # Expected case `non-primitive override from project`: local -> default_provider, which
    #  is `test` in global but `geth` in project; thus it is `geth` in expected.
    # Expected case `merge sub-dictionaries`: `ethereum` is being merged.
    # Expected case `add missing project keys`: `test` is added, so is `sepolia` (nested-example).
    expected = {
        "ethereum": {
            "local": {"default_provider": "node", "required_confirmations": 5},
            "mainnet": {"default_provider": "node"},
            "sepolia": {"default_provider": "alchemy"},
        },
        "test": "foo",
    }
    assert actual == expected


def test_merge_configs_short_circuits():
    """
    Cover all short-circuit cases.
    """
    ex = {"test": "foo"}
    assert merge_configs({}, {}) == {}
    assert merge_configs(ex, {}) == merge_configs({}, ex) == ex


def test_plugin_config_getattr_and_getitem(config):
    config = config.get_config("ethereum")
    assert config.mainnet is not None
    assert config.mainnet == config["mainnet"]


def test_custom_plugin_config_extras():
    class CustomConfig(PluginConfig):
        model_config = SettingsConfigDict(extra="allow")

    config = CustomConfig(foo="123")
    assert "foo" in config
    assert config.foo == "123"
    assert config["foo"] == "123"


def test_config_enum():
    class MyEnum(ConfigEnum):
        FOO = "FOO"
        BAR = "BAR"

    class MyConfig(PluginConfig):
        my_enum: MyEnum

    actual = MyConfig(my_enum="FOO")
    assert actual.my_enum == MyEnum.FOO


def test_contracts_folder_with_hyphen(project):
    with project.temp_config(**{"contracts-folder": "src"}):
        assert project.contracts_folder.name == "src"


def test_custom_network():
    chain_id = 11191919191991918223773
    data = {
        "name": "mytestnet",
        "chain_id": 11191919191991918223773,
        "ecosystem": "ethereum",
    }
    network = CustomNetwork.model_validate(data)
    assert network.name == "mytestnet"
    assert network.chain_id == chain_id
    assert network.ecosystem == "ethereum"
