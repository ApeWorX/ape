import os
import random
import shutil
import string
from pathlib import Path

import pytest
import yaml
from ethpm_types import Compiler
from ethpm_types import ContractInstance as EthPMContractInstance
from ethpm_types import ContractType, Source
from ethpm_types.manifest import PackageManifest

from ape import Contract
from ape.exceptions import ProjectError
from ape.logging import LogLevel
from ape.managers.project import BrownieProject
from ape.utils import create_tempdir

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


@pytest.fixture(scope="session")
def contract_type_0(vyper_contract_type):
    return _make_new_contract(vyper_contract_type, "NewContract_0")


@pytest.fixture(scope="session")
def contract_type_1(vyper_contract_type):
    return _make_new_contract(vyper_contract_type, "NewContract_1")


@pytest.fixture(scope="session")
def existing_source_path(vyper_contract_type, contract_type_0, contracts_folder):
    source_path = contracts_folder / "NewContract_0.json"
    source_path.touch()
    source_path.write_text(contract_type_0.model_dump_json())
    yield source_path
    if source_path.is_file():
        source_path.unlink()


@pytest.fixture
def manifest_with_non_existent_sources(
    existing_manifest, existing_source_path, contract_type_0, contract_type_1
):
    manifest = existing_manifest.model_copy()
    manifest.contract_types["NewContract_0"] = contract_type_0
    manifest.contract_types["NewContract_1"] = contract_type_1
    # Previous refs shouldn't interfere (bugfix related)
    manifest.sources["NewContract_0.json"] = Source(
        content=contract_type_0.model_dump_json(), references=["NewContract_1.json"]
    )
    manifest.sources["NewContract_1.json"] = Source(content=contract_type_1.model_dump_json())
    return manifest


@pytest.fixture
def project_without_deployments(project):
    if project._package_deployments_folder.is_dir():
        shutil.rmtree(project._package_deployments_folder)

    return project


def _make_new_contract(existing_contract: ContractType, name: str):
    source_text = existing_contract.model_dump_json()
    source_text = source_text.replace(f"{existing_contract.name}.vy", f"{name}.json")
    source_text = source_text.replace(existing_contract.name or "", name)
    return ContractType.model_validate_json(source_text)


def test_extract_manifest(project_with_dependency_config):
    # NOTE: Only setting dependency_config to ensure existence of project.
    manifest = project_with_dependency_config.extract_manifest()
    assert type(manifest) is PackageManifest
    assert type(manifest.compilers) is list
    assert manifest.meta == project_with_dependency_config.meta
    assert manifest.compilers == project_with_dependency_config.compiler_data
    assert manifest.deployments == project_with_dependency_config.tracked_deployments


def test_cached_manifest_when_sources_missing(
    ape_project, manifest_with_non_existent_sources, existing_source_path, ape_caplog
):
    """
    Show that if a source is missing, it is OK. This happens when changing branches
    after compiling and sources are only present on one of the branches.
    """
    cache_location = ape_project._cache_folder / "__local__.json"
    if cache_location.is_file():
        cache_location.unlink()

    cache_location.touch()
    name = "NOTEXISTS"
    source_id = f"{name}.json"
    contract_type = ContractType.model_validate(
        {"contractName": name, "abi": [], "sourceId": source_id}
    )
    path = ape_project._cache_folder / source_id
    path.write_text(contract_type.model_dump_json())
    cache_location.write_text(manifest_with_non_existent_sources.model_dump_json())

    manifest = ape_project.cached_manifest

    # Show the contract type does not get added and we don't get the corrupted manifest.
    assert not any(ct.name == name for ct in manifest.contract_types.values())
    assert not any("corrupted. Re-building" in msg for msg in ape_caplog.messages)


def test_create_manifest_when_file_changed_with_cached_references_that_no_longer_exist(
    ape_project, manifest_with_non_existent_sources, existing_source_path
):
    """
    This test is for the condition when you have a cached manifest containing references
    from a source file however those references no longer exist and the source file has changes.
    """

    cache_location = ape_project._cache_folder / "__local__.json"
    if cache_location.is_file():
        cache_location.unlink()

    ape_project._cache_folder.mkdir(exist_ok=True)
    cache_location.touch()
    cache_location.write_text(manifest_with_non_existent_sources.model_dump_json())

    # Change content
    source_text = existing_source_path.read_text()
    existing_source_path.unlink()
    source_text = source_text.replace("uint256[20]", "uint256[25]")
    existing_source_path.write_text(source_text)

    manifest = ape_project.create_manifest()
    assert manifest


def test_create_manifest_empty_files(compilers, mock_compiler, config, ape_caplog):
    """
    Tests again a bug where empty contracts would infinitely compile.
    """

    # Using a random name to prevent async conflicts.
    letters = string.ascii_letters
    name = "".join(random.choice(letters) for _ in range(10))

    with create_tempdir() as temp_dir:
        contracts = temp_dir / "contracts"
        contracts.mkdir()
        file_1 = contracts / f"{name}.__mock__"
        file_1.write_text("")

        with config.using_project(temp_dir) as proj:
            compilers.registered_compilers[".__mock__"] = mock_compiler

            # NOTE: Set levels as close to the operation as possible
            #  to lessen chance of caplog race conditions.
            ape_caplog.set_levels(caplog_level=LogLevel.INFO)

            # Run twice to show use_cache=False works.
            proj.local_project.create_manifest()
            manifest = proj.local_project.create_manifest(use_cache=False)

            assert name in manifest.contract_types
            assert f"{name}.__mock__" in manifest.sources

            ape_caplog.assert_last_log(f"Compiling '{name}.__mock__'.")
            ape_caplog.clear()

            # Ensure is not double compiled!
            proj.local_project.create_manifest()
            assert f"Compiling '{name}.__mock__'." not in ape_caplog.head


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

        link = project.meta.links["apeworx.io"]
        assert link.host == "apeworx.io"
        assert link.scheme == "https"


def test_brownie_project_configure(config, base_projects_directory):
    project_path = base_projects_directory / "BrownieProject"
    expected_config_file = project_path / "ape-config.yaml"
    if expected_config_file.is_file():
        # Left from previous run
        expected_config_file.unlink()

    project = BrownieProject(path=project_path, contracts_folder=Path("contracts"))
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
    actual_from_file = EthPMContractInstance.model_validate_json(deployment_path.read_text())
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
    actual_from_file = EthPMContractInstance.model_validate_json(path.read_text())
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
    actual = EthPMContractInstance.model_validate_json(path.read_text())
    assert actual.address == address
    assert actual.contract_type == contract.contract_type.name
    assert actual.transaction == txn_hash
    assert actual.runtime_bytecode == contract.contract_type.runtime_bytecode


def test_compiler_data_and_update_cache(config, project_path, contracts_folder):
    with config.using_project(project_path, contracts_folder=contracts_folder) as project:
        compiler = Compiler(name="comp", version="1.0.0")
        project.local_project.update_manifest(compilers=[compiler])
        assert project.local_project.manifest.compilers == [compiler]
        assert project.compiler_data == [compiler]


def test_get_project_without_contracts_path(project):
    project_path = WITH_DEPS_PROJECT / "default"
    project = project.get_project(project_path)
    assert project.contracts_folder == project_path / "contracts"


def test_get_project_with_contracts_path(project):
    project_path = WITH_DEPS_PROJECT / "renamed_contracts_folder_specified_in_config"
    project = project.get_project(project_path, project_path / "my_contracts")
    assert project.contracts_folder == project_path / "my_contracts"


def test_get_project_figure_out_contracts_path(project):
    """
    Tests logic where `contracts` is not the contracts folder but it still is able
    to figure it out.
    """
    project_path = WITH_DEPS_PROJECT / "renamed_contracts_folder"
    (project_path / "ape-config.yaml").unlink(missing_ok=True)  # Clean from prior.

    project = project.get_project(project_path)
    assert project.contracts_folder == project_path / "sources"


def test_lookup_path(project_with_source_files_contract):
    project = project_with_source_files_contract
    actual_from_str = project.lookup_path("ContractA.sol")
    actual_from_path = project.lookup_path(Path("ContractA.sol"))
    expected = project.contracts_folder / "ContractA.sol"
    assert actual_from_str == actual_from_path == expected


def test_lookup_path_closest_match(project_with_source_files_contract):
    pm = project_with_source_files_contract
    source_path = pm.contracts_folder / "Contract.json"
    temp_dir_a = pm.contracts_folder / "temp"
    temp_dir_b = temp_dir_a / "tempb"
    nested_source_a = temp_dir_a / "Contract.json"
    nested_source_b = temp_dir_b / "Contract.json"

    def clean():
        # NOTE: Will also delete temp_dir_b.
        if temp_dir_a.is_dir():
            shutil.rmtree(temp_dir_a)

    clean()

    # NOTE: Will also make temp_dir_a.
    temp_dir_b.mkdir(parents=True)

    try:
        # Duplicate contract so that there are multiple with the same name.
        for nested_src in (nested_source_a, nested_source_b):
            nested_src.touch()
            nested_src.write_text(source_path.read_text())

        # Top-level match.
        for base in (source_path, str(source_path), "Contract", "Contract.json"):
            assert pm.lookup_path(base) == source_path, f"Failed to lookup {base}"

        # Nested: 1st level
        for closest in (
            nested_source_a,
            str(nested_source_a),
            "temp/Contract",
            "temp/Contract.json",
        ):
            assert pm.lookup_path(closest) == nested_source_a, f"Failed to lookup {closest}"

        # Nested: 2nd level
        for closest in (
            nested_source_b,
            str(nested_source_b),
            "temp/tempb/Contract",
            "temp/tempb/Contract.json",
        ):
            assert pm.lookup_path(closest) == nested_source_b, f"Failed to lookup {closest}"

    finally:
        clean()


def test_lookup_path_includes_contracts_prefix(project_with_source_files_contract):
    """
    Show we can include the `contracts/` prefix.
    """
    project = project_with_source_files_contract
    actual_from_str = project.lookup_path("contracts/ContractA.sol")
    actual_from_path = project.lookup_path(Path("contracts/ContractA.sol"))
    expected = project.contracts_folder / "ContractA.sol"
    assert actual_from_str == actual_from_path == expected
    assert actual_from_str.is_absolute()
    assert actual_from_path.is_absolute()


def test_sources(project_with_source_files_contract):
    project = project_with_source_files_contract
    assert "ApeContract0.json" in project.sources
    assert project.sources["ApeContract0.json"].content


def test_contracts_folder(project, config):
    # Relaxed to handle xdist resource sharing.
    assert project.contracts_folder.name in ("contracts", "src")

    # Show that even when None in the config, it won't be None here.
    config.contracts_folder = None
    assert config.contracts_folder is None
    assert project.contracts_folder is not None


def test_getattr_contract_not_exists(project):
    expected = (
        r"ProjectManager has no attribute or contract named "
        r"'ThisIsNotAContractThatExists'. However, there is a source "
        r"file named 'ThisIsNotAContractThatExists\.foo', did you mean to "
        r"reference a contract name from this source file\? "
        r"Else, could it be from one of the missing compilers for extensions:.*\?"
    )
    project.contracts_folder.mkdir(exist_ok=True)
    contract = project.contracts_folder / "ThisIsNotAContractThatExists.foo"
    contract.touch()
    with pytest.raises(AttributeError, match=expected):
        _ = project.ThisIsNotAContractThatExists


@pytest.mark.parametrize("iypthon_attr_name", ("_repr_mimebundle_", "_ipython_display_"))
def test_getattr_ipython(mocker, project, iypthon_attr_name):
    spy = mocker.spy(project, "_get_contract")
    getattr(project, iypthon_attr_name)
    # Ensure it does not try to do anything with contracts.
    assert spy.call_count == 0


def test_getattr_ipython_canary_check(mocker, project):
    spy = mocker.spy(project, "_get_contract")
    with pytest.raises(AttributeError):
        getattr(project, "_ipython_canary_method_should_not_exist_")

    # Ensure it does not try to do anything with contracts.
    assert spy.call_count == 0


def test_build_file_only_modified_once(project_with_contract):
    project = project_with_contract
    artifact = project.path / ".build" / "__local__.json"
    _ = project.contracts  # Ensure compiled.

    # NOTE: This is how re-create the bug. Delete the underscore-prefixed
    #  cached object and attempt to re-compile. Previously, the ProjectManager
    #  was relying on an internal cache rather than the external one, and thus
    #  caused the file to get unnecessarily re-made (modified).
    project.local_project._cached_manifest = None

    # Prove the file is not unnecessarily modified.
    time_before = os.path.getmtime(artifact)
    _ = project.contracts
    time_after = os.path.getmtime(artifact)
    assert time_before == time_after


def test_source_paths_excludes_cached_dependencies(project_with_contract):
    """
    Dependencies are ignored from the project's sources.
    Their used sources are imported and part of the final output,
    but just not the input.
    """
    contracts_folder = project_with_contract.contracts_folder
    cache_dir = contracts_folder / ".cache"
    cache_dir.mkdir(exist_ok=True)
    cache_dep_folder = cache_dir / "dep" / "1.0.0"
    cache_dep_folder.mkdir(parents=True, exist_ok=True)
    contract = next(
        x
        for x in contracts_folder.iterdir()
        if x.is_file() and x.suffix == ".json" and not x.stem.startswith("_")
    )
    dep_contract = cache_dep_folder / "contract.json"
    shutil.copy(contract, dep_contract)
    actual = project_with_contract.source_paths
    assert dep_contract not in actual


def test_update_manifest_compilers(project):
    compiler = Compiler(name="comp", version="1.0.0", contractTypes=["foo.txt"])
    project.local_project.update_manifest(compilers=[compiler])
    actual = project.local_project.manifest.compilers
    assert actual == [compiler]

    project.local_project.update_manifest(name="test", version="1.0.0")
    assert project.local_project.manifest.name == "test"
    assert project.local_project.manifest.version == "1.0.0"

    # The compilers should not have changed.
    actual = project.local_project.manifest.compilers
    assert actual == [compiler]

    # Add a new one.
    # NOTE: `update_cache()` will override the fields entirely.
    #   You must include existing fields if you want to merge.
    compiler_2 = Compiler(name="test", version="2.0.0", contractTypes=["bar.txt"])
    project.local_project.update_manifest(compilers=[compiler_2])
    actual = project.local_project.manifest.compilers
    assert actual == [compiler_2]


def test_load_contracts(project_with_contract):
    contracts = project_with_contract.load_contracts()
    assert len(contracts) > 0
    assert contracts == project_with_contract.contracts


def test_load_contracts_after_deleting_same_named_contract(config, compilers, mock_compiler):
    """
    Tests against a scenario where you:

    1. Add and compile a contract
    2. Delete that contract
    3. Add a new contract with same name somewhere else

    Test such that we are able to compile successfully and not get a misleading
    collision error from deleted files.
    """

    with create_tempdir() as path:
        contracts = path / "contracts"
        contracts.mkdir()
        init_contract = contracts / "foo.__mock__"
        init_contract.write_text("LALA")
        with config.using_project(path) as proj:
            compilers.registered_compilers[".__mock__"] = mock_compiler
            result = proj.load_contracts()
            assert "foo" in result

            # Delete file
            init_contract.unlink()

            # Create new contract that yields same name as deleted one.
            new_contract = contracts / "bar.__mock__"
            new_contract.write_text("BAZ")
            mock_compiler.overrides = {"contractName": "foo"}

            result = proj.load_contracts()
            assert "foo" in result


def test_add_compiler_data(project_with_dependency_config):
    # NOTE: Using different project than default to lessen
    #   chance of race-conditions from multi-process test runners.
    project = project_with_dependency_config

    # Load contracts so that any compilers that may exist are present.
    project.load_contracts()
    start_compilers = project.local_project.manifest.compilers or []

    # NOTE: Pre-defining things to lessen chance of race condition.
    compiler = Compiler(name="comp", version="1.0.0", contractTypes=["foo"])
    compiler_2 = Compiler(name="test", version="2.0.0", contractTypes=["bar", "stay"])

    # NOTE: Has same contract as compiler 2 and thus replaces the contract.
    compiler_3 = Compiler(name="test", version="3.0.0", contractTypes=["bar"])

    proj = project.local_project
    argument = [compiler]
    second_arg = [compiler_2]
    third_arg = [compiler_3]
    first_exp = [*start_compilers, compiler]
    final_exp = [*first_exp, compiler_2]

    # Add twice to show it's only added once.
    proj.add_compiler_data(argument)
    proj.add_compiler_data(argument)
    assert proj.manifest.compilers == first_exp

    # NOTE: `add_compiler_data()` will not override existing compilers.
    #   Use `update_cache()` for that.
    proj.add_compiler_data(second_arg)
    assert proj.manifest.compilers == final_exp

    proj.add_compiler_data(third_arg)
    comp = [c for c in proj.manifest.compilers if c.name == "test" and c.version == "2.0.0"][0]
    assert "bar" not in comp.contractTypes

    # Show that compilers without contract types go away.
    (compiler_3.contractTypes or []).append("stay")
    proj.add_compiler_data(third_arg)
    comp_check = [c for c in proj.manifest.compilers if c.name == "test" and c.version == "2.0.0"]
    assert not comp_check

    # Show error on multiple of same compiler.
    compiler_4 = Compiler(name="test123", version="3.0.0", contractTypes=["bar"])
    compiler_5 = Compiler(name="test123", version="3.0.0", contractTypes=["baz"])
    with pytest.raises(ProjectError, match=r".*was given multiple of the same compiler.*"):
        proj.add_compiler_data([compiler_4, compiler_5])

    # Show error when contract type collision (only happens with inputs, else latter replaces).
    compiler_4 = Compiler(name="test321", version="3.0.0", contractTypes=["bar"])
    compiler_5 = Compiler(name="test456", version="9.0.0", contractTypes=["bar"])
    with pytest.raises(ProjectError, match=r".*'bar' collision across compilers.*"):
        proj.add_compiler_data([compiler_4, compiler_5])
