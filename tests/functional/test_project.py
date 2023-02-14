import shutil
from pathlib import Path

import pytest
import yaml
from ethpm_types import ContractInstance as EthPMContractInstance
from ethpm_types import ContractType, Source
from ethpm_types.manifest import PackageManifest

from ape import Contract
from ape.exceptions import ProjectError
from ape.managers.project import BrownieProject

WITH_DEPS_PROJECT = (
    Path(__file__).parent.parent / "integration" / "cli" / "projects" / "with-dependencies"
)


@pytest.fixture
def ape_project(project):
    return project.local_project


@pytest.fixture
def bip122_chain_id(eth_tester_provider):
    return eth_tester_provider.get_block(0).hash.hex()


@pytest.fixture
def base_deployments_path(project, bip122_chain_id):
    return project._package_deployments_folder / bip122_chain_id


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


@pytest.fixture
def existing_manifest(ape_project):
    return ape_project.create_manifest()


@pytest.fixture
def contract_type_0(vyper_contract_type):
    return _make_new_contract(vyper_contract_type, "NewContract_0")


@pytest.fixture
def contract_type_1(vyper_contract_type):
    return _make_new_contract(vyper_contract_type, "NewContract_1")


@pytest.fixture
def existing_source_path(vyper_contract_type, contract_type_0, contracts_folder):
    source_path = contracts_folder / "NewContract_0.json"
    source_path.touch()
    source_path.write_text(contract_type_0.json())
    yield source_path
    if source_path.is_file():
        source_path.unlink()


@pytest.fixture
def manifest_with_non_existent_sources(
    existing_manifest, existing_source_path, contract_type_0, contract_type_1
):
    manifest = existing_manifest.copy()
    manifest.contract_types["NewContract_0"] = contract_type_0
    manifest.contract_types["NewContract_1"] = contract_type_1
    # Previous refs shouldn't interfere (bugfix related)
    manifest.sources["NewContract_0.json"] = Source(
        content=contract_type_0.json(), references=["NewContract_1.json"]
    )
    manifest.sources["NewContract_1.json"] = Source(content=contract_type_1.json())
    return manifest


@pytest.fixture
def project_without_deployments(project):
    if project._package_deployments_folder.is_dir():
        shutil.rmtree(project._package_deployments_folder)

    return project


def _make_new_contract(existing_contract: ContractType, name: str):
    source_text = existing_contract.json()
    source_text = source_text.replace(f"{existing_contract.name}.vy", f"{name}.json")
    source_text = source_text.replace(existing_contract.name or "", name)
    return ContractType.parse_raw(source_text)


def test_extract_manifest(project_with_dependency_config):
    # NOTE: Only setting dependency_config to ensure existence of project.
    manifest = project_with_dependency_config.extract_manifest()
    assert type(manifest) == PackageManifest
    assert type(manifest.compilers) == list
    assert manifest.meta == project_with_dependency_config.meta
    assert manifest.compilers == project_with_dependency_config.compiler_data
    assert manifest.deployments == project_with_dependency_config.tracked_deployments


def test_create_manifest_when_file_changed_with_cached_references_that_no_longer_exist(
    ape_project, manifest_with_non_existent_sources, existing_source_path
):
    # This test is for the condition when you have a cached manifest containing references
    # from a source file however those references no longer exist and the source file has changes.
    cache_location = ape_project._cache_folder / "__local__.json"
    if cache_location.is_file():
        cache_location.unlink()

    cache_location.touch()
    cache_location.write_text(manifest_with_non_existent_sources.json())

    # Change content
    source_text = existing_source_path.read_text()
    existing_source_path.unlink()
    source_text = source_text.replace("uint256[20]", "uint256[25]")
    existing_source_path.write_text(source_text)

    manifest = ape_project.create_manifest()
    assert manifest


def test_meta(temp_config, project):
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
        assert project.meta.authors == ["Test Testerson"]
        assert project.meta.license == "MIT"
        assert project.meta.description == "test"
        assert project.meta.keywords == ["testing"]
        assert "https://apeworx.io" in project.meta.links["apeworx.io"]


def test_brownie_project_configure(config, base_projects_directory):
    project_path = base_projects_directory / "BrownieProject"
    expected_config_file = project_path / "ape-config.yaml"
    if expected_config_file.is_file():
        # Left from previous run
        expected_config_file.unlink()

    project = BrownieProject(path=project_path, contracts_folder="contracts")
    project.process_config_file()
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
    project_without_deployments,
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

    # Even though deployments should be 0, do this to in case x-dist affects it.
    num_deployments_before = len(project_without_deployments.tracked_deployments)

    project_without_deployments.track_deployment(vyper_contract_instance)

    expected_block_hash = eth_tester_provider.get_block(receipt.block_number).hash.hex()
    expected_uri = f"blockchain://{bip122_chain_id}/block/{expected_block_hash}"
    expected_name = contract.contract_type.name
    expected_code = contract.contract_type.runtime_bytecode
    actual_from_file = EthPMContractInstance.parse_raw(deployment_path.read_text())
    actual_from_class = project_without_deployments.tracked_deployments[expected_uri][name]

    assert actual_from_file.address == actual_from_class.address == address
    assert actual_from_file.contract_type == actual_from_class.contract_type == expected_name
    assert actual_from_file.transaction == actual_from_class.transaction == receipt.txn_hash
    assert actual_from_file.runtime_bytecode == actual_from_class.runtime_bytecode == expected_code

    # Use >= to handle xdist.
    assert len(project_without_deployments.tracked_deployments) >= num_deployments_before + 1


def test_track_deployment_from_previously_deployed_contract(
    clean_deployments,
    project_without_deployments,
    vyper_contract_container,
    eth_tester_provider,
    dummy_live_network,
    owner,
    base_deployments_path,
    bip122_chain_id,
):
    receipt = owner.deploy(vyper_contract_container, 0, required_confirmations=0).receipt
    address = receipt.contract_address
    contract = Contract(address, txn_hash=receipt.txn_hash)
    name = contract.contract_type.name

    # Even though deployments should be 0, do this to in case x-dist affects it.
    num_deployments_before = len(project_without_deployments.tracked_deployments)

    project_without_deployments.track_deployment(contract)

    path = base_deployments_path / f"{contract.contract_type.name}.json"
    expected_block_hash = eth_tester_provider.get_block(receipt.block_number).hash.hex()
    expected_uri = f"blockchain://{bip122_chain_id}/block/{expected_block_hash}"
    expected_name = contract.contract_type.name
    expected_code = contract.contract_type.runtime_bytecode
    actual_from_file = EthPMContractInstance.parse_raw(path.read_text())
    actual_from_class = project_without_deployments.tracked_deployments[expected_uri][name]
    assert actual_from_file.address == actual_from_class.address == address
    assert actual_from_file.contract_type == actual_from_class.contract_type == expected_name
    assert actual_from_file.transaction == actual_from_class.transaction == receipt.txn_hash
    assert actual_from_file.runtime_bytecode == actual_from_class.runtime_bytecode == expected_code

    # Use >= to handle xdist.
    assert len(project_without_deployments.tracked_deployments) >= num_deployments_before + 1


def test_track_deployment_from_unknown_contract_missing_txn_hash(
    clean_deployments,
    dummy_live_network,
    owner,
    vyper_contract_container,
    chain,
    project,
):
    snapshot = chain.snapshot()
    contract = owner.deploy(vyper_contract_container, 0, required_confirmations=0)
    chain.restore(snapshot)

    contract = Contract(contract.address)
    with pytest.raises(
        ProjectError,
        match=f"Contract '{contract.contract_type.name}' transaction receipt is unknown.",
    ):
        project.track_deployment(contract)


def test_track_deployment_from_unknown_contract_given_txn_hash(
    clean_deployments,
    project,
    vyper_contract_instance,
    dummy_live_network,
    base_deployments_path,
):
    address = vyper_contract_instance.address
    txn_hash = vyper_contract_instance.txn_hash
    contract = Contract(address, txn_hash=txn_hash)
    project.track_deployment(contract)
    path = base_deployments_path / f"{contract.contract_type.name}.json"
    actual = EthPMContractInstance.parse_raw(path.read_text())
    assert actual.address == address
    assert actual.contract_type == contract.contract_type.name
    assert actual.transaction == txn_hash
    assert actual.runtime_bytecode == contract.contract_type.runtime_bytecode


def test_compiler_data(config, project_path, contracts_folder):
    # See ape-solidity / ape-vyper for better tests
    with config.using_project(project_path, contracts_folder=contracts_folder) as project:
        assert not project.compiler_data


def test_get_project_without_contracts_path(project):
    project_path = WITH_DEPS_PROJECT / "default"
    project = project.get_project(project_path)
    assert project.contracts_folder == project_path / "contracts"


def test_get_project_with_contracts_path(project):
    project_path = WITH_DEPS_PROJECT / "renamed_contracts_folder"
    project = project.get_project(project_path, project_path / "sources")
    assert project.contracts_folder == project_path / "sources"


def test_get_project_figure_out_contracts_path(project):
    """
    Tests logic where `contracts` is not the contracts folder but it still is able
    to figure it out.
    """
    project_path = WITH_DEPS_PROJECT / "renamed_contracts_folder"
    project = project.get_project(project_path)
    assert project.contracts_folder == project_path / "sources"


def test_lookup_path(project_with_source_files_contract):
    project = project_with_source_files_contract
    actual_from_str = project.lookup_path("ContractA.sol")
    actual_from_path = project.lookup_path(Path("ContractA.sol"))
    expected = project.contracts_folder / "ContractA.sol"
    assert actual_from_str == actual_from_path == expected


def test_sources(project_with_source_files_contract):
    project = project_with_source_files_contract
    assert "ApeContract0.json" in project.sources
    assert project.sources["ApeContract0.json"].content
