import shutil
from pathlib import Path
from typing import Dict

import pytest
import yaml
from ethpm_types import ContractInstance as EthPMContractInstance
from ethpm_types.manifest import PackageManifest

from ape import Contract
from ape.exceptions import ProjectError
from ape.managers.project import BrownieProject


@pytest.fixture
def oz_dependencies_config():
    def _create_oz_dependency(version: str) -> Dict:
        return {
            "name": "OpenZeppelin",
            "version": version,
            "github": "OpenZeppelin/openzeppelin-contracts",
        }

    return {"dependencies": [_create_oz_dependency("3.1.0"), _create_oz_dependency("4.4.2")]}


@pytest.fixture
def already_downloaded_dependencies(temp_config, config, oz_dependencies_config):
    manifests_directory = Path(__file__).parent / "data" / "manifests"
    oz_manifests = manifests_directory / "OpenZeppelin"
    oz_manifests_dest = config.packages_folder / "OpenZeppelin"
    shutil.copytree(oz_manifests, oz_manifests_dest)
    with temp_config(oz_dependencies_config):
        yield


@pytest.fixture
def bip122_chain_id(eth_tester_provider):
    return eth_tester_provider.get_block(0).hash.hex()


@pytest.fixture
def base_deployments_path(project_manager, bip122_chain_id):
    return project_manager._project._cache_folder / "deployments" / bip122_chain_id


@pytest.fixture
def deployment_path(vyper_contract_instance, base_deployments_path):
    file_name = f"{vyper_contract_instance.contract_type.name}.json"
    return base_deployments_path / file_name


@pytest.fixture
def contract_block_hash(eth_tester_provider, vyper_contract_instance):
    block_number = vyper_contract_instance.receipt.block_number
    return eth_tester_provider.get_block(block_number).hash.hex()


@pytest.fixture
def clean_deployments(base_deployments_path):
    if base_deployments_path.is_dir():
        shutil.rmtree(str(base_deployments_path))

    yield


def test_two_dependencies_with_same_name(already_downloaded_dependencies, project_manager):
    name = "OpenZeppelin"
    oz_310 = project_manager.dependencies[name]["3.1.0"]
    oz_442 = project_manager.dependencies[name]["4.4.2"]

    assert oz_310.version == "3.1.0"
    assert oz_310.name == name
    assert oz_442.version == "4.4.2"
    assert oz_442.name == name


def test_extract_manifest(dependency_config, project_manager):
    # NOTE: Only setting dependency_config to ensure existence of project.
    manifest = project_manager.extract_manifest()
    assert type(manifest) == PackageManifest
    assert type(manifest.compilers) == list
    assert manifest.meta == project_manager.meta
    assert manifest.compilers == project_manager.compiler_data
    assert manifest.deployments == project_manager.tracked_deployments


def test_meta(temp_config, project_manager):
    meta_config = {
        "meta": {
            "authors": ["Test Testerson"],
            "license": "MIT",
            "description": "test",
            "keywords": ["testing"],
            "links": {"apeworx.io": "https://apeworx.io"},
        }
    }
    with temp_config(meta_config):
        assert project_manager.meta.authors == ["Test Testerson"]
        assert project_manager.meta.license == "MIT"
        assert project_manager.meta.description == "test"
        assert project_manager.meta.keywords == ["testing"]
        assert "https://apeworx.io" in project_manager.meta.links["apeworx.io"]


def test_dependency_with_longer_contracts_folder(
    dependency_config, config, mocker, project_manager
):
    spy = mocker.patch("ape.managers.project.types.yaml")
    _ = project_manager.dependencies
    assert spy.safe_dump.call_args, "Config file never created"
    call_config = spy.safe_dump.call_args[0][0]
    assert call_config["contracts_folder"] == "source/v0.1"


def test_brownie_project_configure(config, base_projects_directory):
    project_path = base_projects_directory / "BrownieProject"
    expected_config_file = project_path / "ape-config.yaml"
    if expected_config_file.is_file():
        # Left from previous run
        expected_config_file.unlink()

    project = BrownieProject(path=project_path, contracts_folder="contracts")
    project.configure()
    assert expected_config_file.is_file()

    with open(expected_config_file) as ape_config_file:
        mapped_config_data = yaml.safe_load(ape_config_file)

    # Ensure Solidity and dependencies configuration mapped correctly
    assert mapped_config_data["solidity"]["version"] == "0.6.12"
    assert mapped_config_data["solidity"]["import_remapping"] == [
        "@openzeppelin/contracts=OpenZeppelin/3.1.0"
    ]
    assert mapped_config_data["dependencies"][0]["name"] == "OpenZeppelin"
    assert mapped_config_data["dependencies"][0]["github"] == "OpenZeppelin/openzeppelin-contracts"
    assert mapped_config_data["dependencies"][0]["version"] == "3.1.0"

    expected_config_file.unlink()


def test_track_deployment(
    clean_deployments,
    project_manager,
    vyper_contract_instance,
    eth_tester_provider,
    deployment_path,
    contract_block_hash,
    dummy_live_network,
    bip122_chain_id,
):
    contract = vyper_contract_instance
    receipt = contract.receipt
    name = contract.contract_type.name
    address = vyper_contract_instance.address
    project_manager.track_deployment(vyper_contract_instance)
    expected_block_hash = eth_tester_provider.get_block(receipt.block_number).hash.hex()
    expected_uri = f"blockchain://{bip122_chain_id}/block/{expected_block_hash}"
    expected_name = contract.contract_type.name
    expected_code = contract.contract_type.runtime_bytecode
    actual_from_file = EthPMContractInstance.parse_raw(deployment_path.read_text())
    actual_from_class = project_manager.tracked_deployments[expected_uri][name]
    assert actual_from_file.address == actual_from_class.address == address
    assert actual_from_file.contract_type == actual_from_class.contract_type == expected_name
    assert actual_from_file.transaction == actual_from_class.transaction == receipt.txn_hash
    assert actual_from_file.runtime_bytecode == actual_from_class.runtime_bytecode == expected_code
    assert len(project_manager.tracked_deployments) == 1


def test_track_deployment_from_previously_deployed_contract(
    clean_deployments,
    project_manager,
    vyper_contract_container,
    eth_tester_provider,
    dummy_live_network,
    owner,
    base_deployments_path,
    bip122_chain_id,
):
    receipt = owner.deploy(vyper_contract_container, required_confirmations=0).receipt
    address = receipt.contract_address
    contract = Contract(address)
    name = contract.contract_type.name
    project_manager.track_deployment(contract)
    path = base_deployments_path / f"{contract.contract_type.name}.json"
    expected_block_hash = eth_tester_provider.get_block(receipt.block_number).hash.hex()
    expected_uri = f"blockchain://{bip122_chain_id}/block/{expected_block_hash}"
    expected_name = contract.contract_type.name
    expected_code = contract.contract_type.runtime_bytecode
    actual_from_file = EthPMContractInstance.parse_raw(path.read_text())
    actual_from_class = project_manager.tracked_deployments[expected_uri][name]
    assert actual_from_file.address == actual_from_class.address == address
    assert actual_from_file.contract_type == actual_from_class.contract_type == expected_name
    assert actual_from_file.transaction == actual_from_class.transaction == receipt.txn_hash
    assert actual_from_file.runtime_bytecode == actual_from_class.runtime_bytecode == expected_code
    assert len(project_manager.tracked_deployments) == 1


def test_track_deployment_from_unknown_contract_missing_txn_hash(
    clean_deployments,
    project_manager,
    vyper_contract_instance,
    dummy_live_network,
):
    contract = Contract(vyper_contract_instance.address)
    with pytest.raises(
        ProjectError,
        match=f"Contract '{contract.contract_type.name}' transaction receipt is unknown.",
    ):
        project_manager.track_deployment(contract)


def test_track_deployment_from_unknown_contract_given_txn_hash(
    clean_deployments,
    project_manager,
    vyper_contract_instance,
    dummy_live_network,
    base_deployments_path,
):
    address = vyper_contract_instance.address
    txn_hash = vyper_contract_instance.txn_hash
    contract = Contract(address, txn_hash=txn_hash)
    project_manager.track_deployment(contract)
    path = base_deployments_path / f"{contract.contract_type.name}.json"
    actual = EthPMContractInstance.parse_raw(path.read_text())
    assert actual.address == address
    assert actual.contract_type == contract.contract_type.name
    assert actual.transaction == txn_hash
    assert actual.runtime_bytecode == contract.contract_type.runtime_bytecode
