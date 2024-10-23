import os
import re
from pathlib import Path
from typing import Optional, Union

import pytest
from pydantic import ValidationError
from pydantic_settings import SettingsConfigDict

from ape.api.config import ApeConfig, ConfigEnum, PluginConfig
from ape.exceptions import ConfigError
from ape.managers.config import CONFIG_FILE_NAME, merge_configs
from ape.types.gas import GasLimit
from ape.utils.os import create_tempdir
from ape_ethereum.ecosystem import EthereumConfig, NetworkConfig
from ape_networks import CustomNetwork
from tests.functional.conftest import PROJECT_WITH_LONG_CONTRACTS_FOLDER

CONTRACTS_FOLDER = "pathsomewhwere"
NUMBER_OF_TEST_ACCOUNTS = 31
YAML_CONTENT = rf"""
contracts_folder: "{CONTRACTS_FOLDER}"

dependencies:
  - name: "openzeppelin"
    github: "OpenZeppelin/openzeppelin-contracts"
    version: "4.5.0"

plugins:
  - name: "hardhat"
  - name: "solidity"
    version: "0.8.1"

test:
  number_of_accounts: "{NUMBER_OF_TEST_ACCOUNTS}"

compile:
  exclude:
    - "exclude_dir"
    - "Excl*.json"
    - r"Ignore\w*\.json"
""".lstrip()
JSON_CONTENT = f"""
{{
    "contracts_folder": "{CONTRACTS_FOLDER}",
    "dependencies": [
        {{
            "name": "openzeppelin",
            "github": "OpenZeppelin/openzeppelin-contracts",
            "version": "4.5.0"
        }}
    ],
    "plugins": [
        {{
            "name": "hardhat"
        }},
        {{
            "name": "solidity",
            "version": "0.8.1"
        }}
    ],
    "test": {{
        "number_of_accounts": "{NUMBER_OF_TEST_ACCOUNTS}"
    }},
    "compile": {{
        "exclude": [
            "exclude_dir",
            "Excl*.json",
            "r\\"Ignore\\\\w*\\\\.json\\""
        ]
    }}
}}
""".lstrip()
PYPROJECT_TOML = rf"""
[tool.ape]
contracts_folder = "{CONTRACTS_FOLDER}"

[[tool.ape.dependencies]]
name = "openzeppelin"
github = "OpenZeppelin/openzeppelin-contracts"
version = "4.5.0"

[[tool.ape.plugins]]
name = "hardhat"

[[tool.ape.plugins]]
name = "solidity"
version = "0.8.1"

[tool.ape.test]
number_of_accounts = {NUMBER_OF_TEST_ACCOUNTS}

[tool.ape.compile]
exclude = ["exclude_dir", "Excl*.json", 'r"Ignore\w*\.json"']
""".lstrip()
EXT_TO_CONTENT = {
    ".yml": YAML_CONTENT,
    ".yaml": YAML_CONTENT,
    ".json": JSON_CONTENT,
    ".toml": PYPROJECT_TOML,
}


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


@pytest.mark.parametrize(
    "file", ("ape-config.yml", "ape-config.yaml", "ape-config.json", "pyproject.toml")
)
def test_validate_file(file):
    content = EXT_TO_CONTENT[Path(file).suffix]
    with create_tempdir() as temp_dir:
        path = temp_dir / file
        path.write_text(content)
        actual = ApeConfig.validate_file(path)

    assert actual.contracts_folder == CONTRACTS_FOLDER
    assert actual.test.number_of_accounts == NUMBER_OF_TEST_ACCOUNTS
    assert len(actual.dependencies) == 1
    assert actual.dependencies[0]["name"] == "openzeppelin"
    assert actual.dependencies[0]["github"] == "OpenZeppelin/openzeppelin-contracts"
    assert actual.dependencies[0]["version"] == "4.5.0"
    assert actual.plugins == [{"name": "hardhat"}, {"name": "solidity", "version": "0.8.1"}]
    assert re.compile("Ignore\\w*\\.json") in actual.compile.exclude
    assert "exclude_dir" in actual.compile.exclude
    assert ".cache" in actual.compile.exclude
    assert "Excl*.json" in actual.compile.exclude


def test_validate_file_expands_env_vars():
    secret = "mycontractssecretfolder"
    env_var_name = "APE_TEST_CONFIG_SECRET_CONTRACTS_FOLDER"
    os.environ[env_var_name] = secret

    try:
        with create_tempdir() as temp_dir:
            file = temp_dir / "ape-config.yaml"
            file.write_text(f"contracts_folder: ${env_var_name}")

            actual = ApeConfig.validate_file(file)
            assert actual.contracts_folder == secret
    finally:
        if env_var_name in os.environ:
            del os.environ[env_var_name]


def test_validate_file_shows_linenos():
    with create_tempdir() as temp_dir:
        file = temp_dir / "ape-config.yaml"
        file.write_text("name: {'test': 123}")

        expected = (
            f"'{temp_dir / 'ape-config.yaml'}' is invalid!"
            "\nInput should be a valid string\n-->1: name: {'test': 123}"
        )
        with pytest.raises(ConfigError) as err:
            _ = ApeConfig.validate_file(file)

        assert expected in str(err.value)


def test_validate_file_shows_linenos_handles_lists():
    with create_tempdir() as temp_dir:
        file = temp_dir / "ape-config.yaml"
        file.write_text("deployments:\n  ethereum:\n   sepolia:\n      - foo: bar")
        with pytest.raises(ConfigError) as err:
            _ = ApeConfig.validate_file(file)

        assert str(file) in str(err.value)
        assert "sepolia:" in str(err.value)
        assert "-->4" in str(err.value)


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
    sep_cfg = _sepolia_with_gas_limit("4D2")["ethereum"]["sepolia"]
    with pytest.raises(ValidationError, match="Gas limit hex str must include '0x' prefix."):
        NetworkConfig.model_validate(sep_cfg)


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


def test_from_overrides():
    class MyConfig(PluginConfig):
        foo: int = 0

    actual = MyConfig.from_overrides({"foo": 1})
    assert actual.foo == 1


def test_from_overrides_updates_when_default_is_empty_dict():
    class SubConfig(PluginConfig):
        foo: int = 0
        bar: int = 1

    class MyConfig(PluginConfig):
        sub: dict[str, dict[str, SubConfig]] = {}

    overrides = {"sub": {"baz": {"test": {"foo": 5}}}}
    actual = MyConfig.from_overrides(overrides)
    assert actual.sub == {"baz": {"test": SubConfig(foo=5, bar=1)}}


def test_from_overrides_shows_errors_in_project_config():
    class MyConfig(PluginConfig):
        foo: int = 0

    with create_tempdir() as tmp_path:
        file = tmp_path / "ape-config.yaml"
        file.write_text("foo: [1,2,3]")

        with pytest.raises(ConfigError) as err:
            _ = MyConfig.from_overrides({"foo": [1, 2, 3]}, project_path=tmp_path)

        assert "-->1: foo: [1,2,3]" in str(err.value)


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
    config_file.write_text(config_content, encoding="utf8")
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


def test_merge_configs_wrong_type():
    cfg_0 = {"foo": 123}
    cfg_1 = {"foo": {"bar": 123}}
    actual = merge_configs(cfg_0, cfg_1)
    assert actual["foo"] == {"bar": 123}
    actual = merge_configs(cfg_1, cfg_0)
    assert actual["foo"] == 123


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


def test_get_config(config):
    actual = config.get_config("ethereum")
    assert isinstance(actual, EthereumConfig)


def test_get_config_hyphen_in_plugin_name(config):
    """
    Tests against a bug noticed with ape-polygon-zkevm installed
    on Ape 0.8.0 release where the config no longer worked.
    """

    class CustomConfig(PluginConfig):
        x: int = 123

    mock_cfg_with_hyphens = CustomConfig
    original_method = config.local_project.config._get_config_plugin_classes

    # Hack in the fake plugin to test the behavior.
    def hacked_in_method():
        yield from [*list(original_method()), ("mock-plugin", mock_cfg_with_hyphens)]

    config.local_project.config._get_config_plugin_classes = hacked_in_method

    try:
        cfg = config.get_config("mock-plugin")
        assert isinstance(cfg, CustomConfig)
        assert cfg.x == 123

    finally:
        config.local_project.config._get_config_plugin_classes = original_method


def test_get_config_unknown_plugin(config):
    """
    Simulating reading plugin configs w/o those plugins installed.
    """
    actual = config.get_config("thisshouldnotbeinstalled")
    assert isinstance(actual, PluginConfig)


def test_get_config_invalid_plugin_config(project):
    with project.temp_config(node={"ethereum": [1, 2]}):
        # Show project's ApeConfig model works.
        with pytest.raises(ConfigError):
            project.config.get_config("node")

        # Show the manager-wrapper also works
        # (simple wrapper for local project's config,
        # but at one time pointlessly overrode the `get_config()`
        # which caused issues).
        with pytest.raises(ConfigError):
            project.config_manager.get_config("node")


def test_write_to_disk_json(config):
    with create_tempdir() as base_path:
        path = base_path / "config.json"
        config.write_to_disk(path)
        assert path.is_file()


def test_write_to_disk_yaml(config):
    with create_tempdir() as base_path:
        path = base_path / "config.yaml"
        config.write_to_disk(path)
        assert path.is_file()


def test_write_to_disk_txt(config):
    with create_tempdir() as base_path:
        path = base_path / "config.txt"
        with pytest.raises(ConfigError, match=f"Unsupported destination file type '{path}'."):
            config.write_to_disk(path)


def test_dependencies_not_list_of_dicts(project):
    # NOTE: `project:` is a not a user-facing config, only
    #   for internal Ape.
    data = {"dependencies": 123, "project": str(project.path)}
    expected = "Expecting dependencies: to be iterable. Received: int"
    with pytest.raises(ConfigError, match=expected):
        _ = ApeConfig.model_validate(data)


def test_dependencies_list_of_non_dicts(project):
    # NOTE: `project:` is a not a user-facing config, only
    #   for internal Ape.
    data = {"dependencies": [123, 123], "project": str(project.path)}
    expected = "Expecting mapping for dependency. Received: int."
    with pytest.raises(ConfigError, match=expected):
        _ = ApeConfig.model_validate(data)


def test_project_level_settings(project):
    """
    Settings can be configured in an ape-config.yaml file
    that are not part of any plugin. This test ensures that
    works.
    """
    # NOTE: Using strings for the values to show simple validation occurs.
    with project.temp_config(my_string="my_string", my_int=123, my_bool=True):
        assert project.config.my_string == "my_string"
        assert project.config.my_int == 123
        assert project.config.my_bool is True
