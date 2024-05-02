from pathlib import Path
from typing import Dict, Optional, Union

import pytest
from pydantic_settings import SettingsConfigDict

from ape.api import ConfigEnum, PluginConfig
from ape.api.networks import LOCAL_NETWORK_NAME
from ape.managers.config import (
    CONFIG_FILE_NAME,
    ConfigManager,
    DeploymentConfigCollection,
    merge_configs,
)
from ape.types import GasLimit
from ape.utils import create_tempdir
from ape_ethereum.ecosystem import NetworkConfig
from ape_networks import CustomNetwork
from tests.functional.conftest import PROJECT_WITH_LONG_CONTRACTS_FOLDER


def test_deployments(networks_connected_to_tester, owner, vyper_contract_container, config):
    networks = networks_connected_to_tester  # Connection needs to lookup config.

    # First, obtain a "previously-deployed" contract.
    instance = vyper_contract_container.deploy(1000200000, sender=owner)
    address = instance.address

    # Create a config using this new contract for a "later time".
    data = {
        **_create_deployments(address=address, contract_name=instance.contract_type.name),
        "valid_ecosystems": {"ethereum": networks.ethereum},
        "valid_networks": [LOCAL_NETWORK_NAME],
    }
    deploy_config = DeploymentConfigCollection(root=data)
    assert deploy_config.root["ethereum"]["local"][0]["address"] == address

    orig = config.deployments
    config.deployments = deploy_config
    try:
        # Ensure we can reference the deployment on the contract.
        deployment = vyper_contract_container.deployments[0]
    finally:
        config.deployments = orig

    assert deployment.address == instance.address


def test_deployments_integer_type_addresses(networks):
    data = {
        **_create_deployments(address=0x0C25212C557D00024B7CA3DF3238683A35541354),
        "valid_ecosystems": {"ethereum": networks.ethereum},
        "valid_networks": [LOCAL_NETWORK_NAME],
    }
    config = DeploymentConfigCollection(root=data)
    assert (
        config.root["ethereum"]["local"][0]["address"]
        == "0x0c25212c557d00024b7Ca3df3238683A35541354"
    )


@pytest.mark.parametrize(
    "ecosystem_names,network_names,err_part",
    [(["ERRORS"], ["mainnet"], "ecosystem"), (["ethereum"], ["ERRORS"], "network")],
)
def test_deployments_bad_value(
    ecosystem_names, network_names, err_part, ape_caplog, plugin_manager
):
    deployments = _create_deployments()
    all_ecosystems = dict(plugin_manager.ecosystems)
    ecosystem_dict = {e: all_ecosystems[e] for e in ecosystem_names if e in all_ecosystems}
    data = {**deployments, "valid_ecosystems": ecosystem_dict, "valid_networks": network_names}
    ape_caplog.assert_last_log_with_retries(
        lambda: DeploymentConfigCollection(root=data),
        f"Invalid {err_part}",
    )


def _create_deployments(
    ecosystem_name: str = "ethereum",
    network_name: str = "local",
    address: Union[int, str] = "0x0C25212C557D00024B7CA3DF3238683A35541354",
    contract_name: Optional[str] = "MyContract",
) -> Dict:
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


def test_ethereum_network_configs(config, temp_config):
    eth_config = {"ethereum": {"goerli": {"default_provider": "test"}}}
    with temp_config(eth_config):
        actual = config.get_config("ethereum")
        assert actual.goerli.default_provider == "test"

        # Ensure that non-updated fields remain unaffected
        assert actual.goerli.block_time == 15


def test_network_gas_limit_default(config):
    eth_config = config.get_config("ethereum")

    assert eth_config.goerli.gas_limit == "auto"
    assert eth_config.local.gas_limit == "max"


def _goerli_with_gas_limit(gas_limit: GasLimit) -> dict:
    return {
        "ethereum": {
            "goerli": {
                "default_provider": "test",
                "gas_limit": gas_limit,
            }
        }
    }


@pytest.mark.parametrize("gas_limit", ("auto", "max"))
def test_network_gas_limit_string_config(gas_limit, config, temp_config):
    eth_config = _goerli_with_gas_limit(gas_limit)

    with temp_config(eth_config):
        actual = config.get_config("ethereum")

        assert actual.goerli.gas_limit == gas_limit

        # Local configuration is unaffected
        assert actual.local.gas_limit == "max"


@pytest.mark.parametrize("gas_limit", (1234, "1234", 0x4D2, "0x4D2"))
def test_network_gas_limit_numeric_config(gas_limit, config, temp_config):
    eth_config = _goerli_with_gas_limit(gas_limit)

    with temp_config(eth_config):
        actual = config.get_config("ethereum")

        assert actual.goerli.gas_limit == 1234

        # Local configuration is unaffected
        assert actual.local.gas_limit == "max"


def test_network_gas_limit_invalid_numeric_string(config, temp_config):
    """
    Test that using hex strings for a network's gas_limit config must be
    prefixed with '0x'
    """
    eth_config = _goerli_with_gas_limit("4D2")
    with pytest.raises(ValueError, match="Gas limit hex str must include '0x' prefix."):
        with temp_config(eth_config):
            pass


def test_dependencies(project_with_dependency_config, config):
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


@pytest.mark.parametrize("override_0,override_1", [(True, {"foo": 0}), ({"foo": 0}, True)])
def test_plugin_config_with_union_dicts(override_0, override_1):
    class SubConfig(PluginConfig):
        bool_or_dict: Union[bool, Dict] = True
        dict_or_bool: Union[Dict, bool] = {}

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
    config.load(force_reload=True)
    assert config.get_config("test").number_of_accounts == 11
    config_file.unlink(missing_ok=True)


def test_merge_configs():
    """
    The test covers most cases in `merge_config()`. See comment below explaining
    `expected`.
    """
    global_config = {
        "ethereum": {
            "mainnet": {"default_provider": "geth"},
            "local": {"default_provider": "test", "required_confirmations": 5},
        }
    }
    project_config = {
        "ethereum": {
            "local": {"default_provider": "geth"},
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
            "local": {"default_provider": "geth", "required_confirmations": 5},
            "mainnet": {"default_provider": "geth"},
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


def test_config_manager_loads_on_init(config):
    """
    This is needed or else tools may interact with the config manager
    before it has processed the config file.
    """
    name = "nametestvalidate"

    with create_tempdir() as path:
        config = f"name: {name}"
        (path / "ape-config.yaml").write_text(config)
        manager = ConfigManager(REQUEST_HEADER={}, DATA_FOLDER=Path.cwd(), PROJECT_FOLDER=path)
        assert manager.name == name


def test_load_does_not_call_project_manager(temp_config, config):
    """
    It is highly critical that `load()` does not call anything from
    `project_manager` as it is not loaded yet in the manager access mixin.
    """
    orig = config.project_manager.path
    path = Path("_should_not_be_in_parents_")
    try:
        with temp_config({"contracts_folder": "src"}):
            config.project_manager.path = path
            assert config.load(force_reload=True)
            assert path.name not in [x.name for x in config.contracts_folder.parents]
    finally:
        config.project_manager.path = orig


def test_contracts_folder_with_hyphen(temp_config):
    with temp_config({"contracts-folder": "src"}) as project:
        assert project.contracts_folder.name == "src"


def test_compiler_cache_folder(temp_config):
    with temp_config(
        {"contracts_folder": "smarts", "compile": {"cache_folder": ".cash"}}
    ) as project:
        assert project.contracts_folder.name == "smarts"
        assert project.compiler_cache_folder.name == ".cash"
        assert str(project.contracts_folder) not in str(project.compiler_cache_folder)


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
