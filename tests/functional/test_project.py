import json
import re
import shutil
from pathlib import Path

import pytest
from ethpm_types import Compiler, ContractType, PackageManifest, Source
from ethpm_types.manifest import PackageName
from pydantic_core import Url

from ape import Project
from ape.contracts import ContractContainer
from ape.exceptions import ProjectError
from ape.logging import LogLevel
from ape_pm import BrownieProject
from tests.conftest import skip_if_plugin_installed


@pytest.fixture(scope="module")
def projects_path():
    return Path(__file__).parent.parent / "integration" / "cli" / "projects"


@pytest.fixture(scope="module")
def project_path(projects_path):
    return projects_path / "with-dependencies"


@pytest.fixture
def project_with_contracts(project_path):
    return Project(project_path)


@pytest.fixture
def tmp_project(project_path):
    real_project = Project(project_path)
    # Copies contracts and stuff into a temp folder
    # and returns a project around the temp folder.
    with real_project.isolate_in_tempdir() as tmp_project:
        yield tmp_project


@pytest.fixture
def contract_type():
    return make_contract("FooContractFromManifest")


@pytest.fixture
def manifest(contract_type):
    return make_manifest(contract_type)


@pytest.fixture
def contract_block_hash(eth_tester_provider, vyper_contract_instance):
    block_number = vyper_contract_instance.creation_metadata.block
    return eth_tester_provider.get_block(block_number).hash.hex()


@pytest.fixture
def project_from_manifest(manifest):
    return Project.from_manifest(manifest)


def make_contract(name: str = "test") -> ContractType:
    return ContractType.model_validate(
        {
            "contractName": name,
            "sourceId": f"contracts/{name}.json",
            "abi": [],
        }
    )


def make_manifest(*contracts: ContractType) -> PackageManifest:
    sources = {
        ct.source_id: Source(content=ct.model_dump_json(by_alias=True, mode="json"))
        for ct in contracts
    }
    contract_types = {c.name: c for c in contracts}
    model = {"contractTypes": contract_types, "sources": sources}
    return PackageManifest.model_validate(model)


def test_path(project):
    assert project.path is not None


def test_name(project):
    assert project.name == project.path.name


def test_name_from_config(project):
    with project.temp_config(name="foo-bar"):
        assert project.name == "foo-bar"


@pytest.mark.parametrize("name", ("contracts", "sources"))
def test_contracts_folder_from_config(project, name):
    with project.temp_config(contracts_folder=name):
        assert project.contracts_folder == project.path / name


def test_contracts_folder_same_as_root_path(project):
    with project.temp_config(contracts_folder="."):
        assert project.contracts_folder == project.path


def test_contracts_folder_deduced(tmp_project):
    new_project_path = tmp_project.path / "new"
    new_project_path.mkdir()
    contracts_folder = new_project_path / "sources"
    contracts_folder.mkdir()
    contract = contracts_folder / "tryme.json"
    abi = [{"name": "foo", "type": "fallback", "stateMutability": "nonpayable"}]
    contract.write_text(json.dumps(abi))
    new_project = Project(new_project_path)
    actual = new_project.contracts_folder
    assert actual == contracts_folder


def test_reconfigure(project):
    project.reconfigure(compile={"exclude": ["first", "second"]})
    assert {"first", "second"}.issubset(set(project.config.compile.exclude))


def test_isolate_in_tempdir(project):
    # Purposely not using `tmp_project` fixture.
    with project.isolate_in_tempdir() as tmp_project:
        assert tmp_project.path != project.path
        assert tmp_project.in_tempdir
        # Manifest should have been created by default.
        assert not tmp_project.manifest_path.is_file()


def test_in_tempdir(project, tmp_project):
    assert not project.in_tempdir
    assert tmp_project.in_tempdir


def test_Project(project_path):
    # Purpose not using `project_with_contracts` fixture.
    project = Project(project_path)
    project.manifest_path.unlink(missing_ok=True)
    assert project.path == project_path
    # Manifest should have been created by default.
    assert not project.manifest_path.is_file()


def test_contracts_iter(tmp_project):
    actual = set(iter(tmp_project.contracts))
    assert actual == {"Project", "Other"}


def test_contracts_detect_change(tmp_project, ape_caplog):
    path = tmp_project.contracts_folder / "Other.json"
    content = path.read_text()
    assert "foo" in content, "Test setup failed. Unexpected file content."

    # Must be compiled first.
    with ape_caplog.at_level(LogLevel.INFO):
        contracts = tmp_project.load_contracts()
        assert "Other" in contracts
        ape_caplog.assert_last_log("Compiling")

        ape_caplog.clear()

        # No logs as it doesn't need to re-compile.
        tmp_project.load_contracts()
        assert not ape_caplog.head

        # Make a change to the file.
        new_content = content.replace("foo", "bar")
        assert "bar" in new_content, "Test setup failed. Unexpected file content."
        path.unlink()
        path.write_text(new_content)

        # Prove re-compiles.
        contracts = tmp_project.load_contracts()
        assert "Other" in contracts
        ape_caplog.assert_last_log("Compiling")


def test_getattr(tmp_project):
    actual = tmp_project.Other
    assert type(actual) is ContractContainer


def test_getattr_not_exists(tmp_project):
    with pytest.raises(AttributeError):
        _ = tmp_project.nope


def test_getattr_detects_changes(tmp_project):
    source_id = tmp_project.Other.contract_type.source_id
    new_abi = {
        "inputs": [],
        "name": "retrieve",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
    content = json.dumps([new_abi])
    path = tmp_project.sources.lookup(source_id)
    assert path
    path.unlink(missing_ok=True)
    path.write_text(content)
    # Should have re-compiled.
    contract = tmp_project.Other
    assert "retrieve" in contract.contract_type.methods


def test_getattr_empty_contract(tmp_project):
    """
    Tests against a condition where would infinitely compile.
    """
    source_id = tmp_project.Other.contract_type.source_id
    path = tmp_project.sources.lookup(source_id)
    path.unlink(missing_ok=True)
    path.write_text("")
    # Should have re-compiled.
    contract = tmp_project.Other
    assert not contract.contract_type.methods


@skip_if_plugin_installed("vyper", "solidity")
def test_getattr_same_name_as_source_file(project_with_source_files_contract):
    missing_exts = set()
    for src_id in project_with_source_files_contract.sources:
        if (
            Path(src_id).suffix
            not in project_with_source_files_contract.compiler_manager.registered_compilers
        ):
            missing_exts.add(Path(src_id).suffix)

    expected = (
        r"'LocalProject' object has no attribute 'ContractA'\. "
        r"Also checked extra\(s\) 'contracts, manifest'\. "
        r"However, there is a source file named 'ContractA\.sol', "
        r"did you mean to reference a contract name from this source file\? "
        r"Else, could it be from one of the missing compilers for extensions: "
        rf'{re.escape(", ".join(sorted(list(missing_exts))))}\?'
    )
    with pytest.raises(AttributeError, match=expected):
        _ = project_with_source_files_contract.ContractA


@pytest.mark.parametrize("iypthon_attr_name", ("_repr_mimebundle_", "_ipython_display_"))
def test_getattr_ipython(tmp_project, iypthon_attr_name):
    # Remove contract types, if there for some reason is any.
    tmp_project.manifest.contract_types = {}
    getattr(tmp_project, iypthon_attr_name)
    # Prove it did not compile looking for these names.
    assert not tmp_project.manifest.contract_types


def test_getattr_ipython_canary_check(tmp_project):
    # Remove contract types, if there for some reason is any.
    tmp_project.manifest.contract_types = {}
    with pytest.raises(AttributeError):
        getattr(tmp_project, "_ipython_canary_method_should_not_exist_")

    # Prove it did not compile looking for this.
    assert not tmp_project.manifest.contract_types


def test_getitem(tmp_project):
    actual = tmp_project["Project"]
    assert type(actual) is ContractContainer


def test_Project_config_override(project_path):
    contracts_folder = project_path / "my_contracts"
    config = {"contracts_folder": contracts_folder.name}
    project = Project(project_path, config_override=config)
    assert project.contracts_folder == contracts_folder


def test_Project_from_manifest(manifest):
    # Purposely not using `project_from_manifest` fixture.
    project = Project.from_manifest(manifest)
    assert isinstance(project, Project)
    assert project.manifest == manifest


def test_Project_from_manifest_contracts_iter(contract_type, project_from_manifest):
    actual = set(iter(project_from_manifest.contracts))
    assert actual == {"FooContractFromManifest"}


def test_Project_from_manifest_getattr(contract_type, project_from_manifest):
    expected = ContractContainer(contract_type)
    actual = project_from_manifest.FooContractFromManifest
    assert isinstance(actual, ContractContainer)
    assert actual == expected


def test_Project_from_manifest_getitem(contract_type, project_from_manifest):
    expected = ContractContainer(contract_type)
    assert project_from_manifest["FooContractFromManifest"] == expected


def test_meta(project):
    meta_config = {
        "meta": {
            "authors": ["Apealicious Jones"],
            "license": "MIT",
            "description": "Zoologist meme protocol",
            "keywords": ["Indiana", "Knight's Templar"],
            "links": {"apeworx.io": "https://apeworx.io"},
        }
    }
    with project.temp_config(**meta_config):
        assert project.meta.authors == ["Apealicious Jones"]
        assert project.meta.license == "MIT"
        assert project.meta.description == "Zoologist meme protocol"
        assert project.meta.keywords == ["Indiana", "Knight's Templar"]
        assert project.meta.links == {"apeworx.io": Url("https://apeworx.io")}


def test_deployments_track_and_instance_map(tmp_project, mock_sepolia, vyper_contract_instance):
    # The contract must be part of the project to track with the project manifest.
    contract_type = vyper_contract_instance.contract_type
    tmp_project.manifest.contract_types = {contract_type.name: contract_type}
    tmp_project.deployments.track(vyper_contract_instance)
    instance = next(iter(tmp_project.deployments), None)
    assert instance is not None

    assert instance.contract_type == f"{contract_type.source_id}:{contract_type.name}"
    assert tmp_project.deployments.instance_map != {}

    bip122_chain_id = tmp_project.provider.get_block(0).hash.hex()
    expected_uri = f"blockchain://{bip122_chain_id[2:]}/block/"
    for key in tmp_project.deployments.instance_map.keys():
        if key.startswith(expected_uri):
            return

    assert False, "Failed to find expected URI"


def test_extract_manifest(tmp_project, mock_sepolia, vyper_contract_instance):
    contract_type = vyper_contract_instance.contract_type
    tmp_project.manifest.contract_types = {contract_type.name: contract_type}
    tmp_project.deployments.track(vyper_contract_instance)

    manifest = tmp_project.extract_manifest()
    assert type(manifest) is PackageManifest
    assert manifest.meta == tmp_project.meta
    assert PackageName("manifest-dependency") in (manifest.dependencies or {})
    bip122_chain_id = tmp_project.provider.get_block(0).hash.hex()
    expected_uri = f"blockchain://{bip122_chain_id[2:]}"
    for key in manifest.deployments or {}:
        if key.startswith(expected_uri):
            return

    assert False, "Failed to find expected deployment URI"


def test_extract_manifest_when_sources_missing(tmp_project):
    """
    Show that if a source is missing, it is OK. This happens when changing branches
    after compiling and sources are only present on one of the branches.
    """
    contract = make_contract("notreallyhere")
    tmp_project.manifest.contract_types = {contract.name: contract}
    manifest = tmp_project.extract_manifest()

    # Source is skipped because missing.
    assert "notreallyhere" not in manifest.contract_types


def test_exclusions(tmp_project):
    exclusions = ["Other.json", "*Excl*"]
    exclude_config = {"compile": {"exclude": exclusions}}
    with tmp_project.temp_config(**exclude_config):
        for exclusion in exclusions:
            assert exclusion in tmp_project.exclusions


def test_sources_lookup(tmp_project):
    source_id = tmp_project.Other.contract_type.source_id
    path = tmp_project.sources.lookup(source_id)
    assert path == tmp_project.path / source_id


def test_sources_lookup_mismatched_extension(tmp_project):
    source_id = tmp_project.Other.contract_type.source_id
    source_id = source_id.replace(".json", ".js")
    path = tmp_project.sources.lookup(source_id)
    assert path is None


def test_sources_lookup_closest_match(project_with_source_files_contract):
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
            assert pm.sources.lookup(base) == source_path, f"Failed to lookup {base}"

        # Nested: 1st level
        for closest in (
            nested_source_a,
            str(nested_source_a),
            "temp/Contract",
            "temp/Contract.json",
        ):
            actual = pm.sources.lookup(closest)
            expected = nested_source_a
            assert actual == expected, f"Failed to lookup {closest}"

        # Nested: 2nd level
        for closest in (
            nested_source_b,
            str(nested_source_b),
            "temp/tempb/Contract",
            "temp/tempb/Contract.json",
        ):
            actual = pm.sources.lookup(closest)
            expected = nested_source_b
            assert actual == expected, f"Failed to lookup {closest}"

    finally:
        clean()


def test_sources_lookup_includes_contracts_prefix(project_with_source_files_contract):
    """
    Show we can include the `contracts/` prefix.
    """
    project = project_with_source_files_contract
    actual_from_str = project.sources.lookup("contracts/ContractA.sol")
    actual_from_path = project.sources.lookup(Path("contracts/ContractA.sol"))
    expected = project.contracts_folder / "ContractA.sol"
    assert actual_from_str == actual_from_path == expected
    assert actual_from_str.is_absolute()
    assert actual_from_path.is_absolute()


def test_sources_paths_exclude(tmp_project):
    exclude_config = {"compile": {"exclude": ["Other.json"]}}
    with tmp_project.temp_config(**exclude_config):
        # Show default excludes also work, such as a .DS_Store file.
        ds_store = tmp_project.contracts_folder / ".DS_Store"
        ds_store.write_bytes(b"asdfasf")

        # Show anything in compiler-cache is ignored.
        cache = tmp_project.contracts_folder / ".cache"
        cache.mkdir(exist_ok=True)
        random_file = cache / "dontmindme.json"
        random_file.write_text("what, this isn't json?!")

        path_ids = {
            f"{tmp_project.contracts_folder.name}/{src.name}" for src in tmp_project.sources.paths
        }
        excluded = {".DS_Store", "Other.json", ".cache/dontmindme.json"}
        for actual in (path_ids, tmp_project.sources):
            for exclusion in excluded:
                expected = f"{tmp_project.contracts_folder.name}/{exclusion}"
                assert expected not in actual


def test_sources_is_excluded(project_with_contracts):
    exclude_cfg = {"compile": {"exclude": ["exclude_dir/*", "Excl*.json"]}}
    source_ids = ("contracts/exclude_dir/UnwantedContract.json", "contracts/Exclude.json")
    with project_with_contracts.temp_config(**exclude_cfg):
        for source_id in source_ids:
            path = project_with_contracts.path / source_id
            assert project_with_contracts.sources.is_excluded(path)


def test_sources_items(project_with_contracts):
    actual = list(project_with_contracts.sources.items())
    assert len(actual) > 0
    assert isinstance(actual[0], tuple)
    assert "contracts/Other.json" in [x[0] for x in actual]
    assert isinstance(actual[0][1], Source)


def test_sources_keys(project_with_contracts):
    actual = list(project_with_contracts.sources.keys())
    assert "contracts/Other.json" in actual


def test_sources_values(project_with_contracts):
    actual = list(project_with_contracts.sources.values())
    assert all(isinstance(x, Source) for x in actual)


def test_dependencies_iter(tmp_project):
    actual = [x for x in tmp_project.dependencies]
    names = [x.name for x in actual]
    assert "manifest-dependency" in names


def test_dependencies_getitem(tmp_project):
    actual = tmp_project.dependencies["manifest-dependency"]
    assert "local" in actual


def test_dependencies_get_dependency(tmp_project):
    actual = tmp_project.dependencies.get_dependency("manifest-dependency", "local")
    assert actual.name == "manifest-dependency"
    assert actual.version == "local"


def test_dependency_project(tmp_project):
    dependency = tmp_project.dependencies.get_dependency("renamed-contracts-folder", "local")
    project = dependency.project
    assert next(iter(project.contracts), "fail") == "renamed_contracts_folder"
    assert "renamed_contracts_folder" in project


def test_dependency_project_only_manifest(tmp_project):
    """
    Shows you can use manifests as dependencies directly.
    """
    dependency = tmp_project.dependencies.get_dependency("manifest-dependency", "local")
    project = dependency.project
    # Happens to also be the name of the contract.
    assert next(iter(project.contracts), "fail") == "manifest-dependency"
    assert "manifest-dependency" in project


def test_update_manifest(tmp_project):
    compiler = Compiler(name="comp", version="1.0.0", contractTypes=["foo.txt"])
    tmp_project.update_manifest(compilers=[compiler])
    actual = tmp_project.manifest.compilers
    assert actual == [compiler]

    tmp_project.update_manifest(name="test", version="1.0.0")
    assert tmp_project.manifest.name == "test"
    assert tmp_project.manifest.version == "1.0.0"

    # The compilers should not have changed.
    actual = tmp_project.manifest.compilers
    assert actual == [compiler]


def test_load_contracts(tmp_project):
    contracts = tmp_project.load_contracts()
    assert tmp_project.manifest_path.is_file()
    assert len(contracts) > 0
    contracts_forced = tmp_project.load_contracts(use_cache=False)
    assert contracts_forced == contracts


def test_load_contracts_after_deleting_same_named_contract(tmp_project, compilers, mock_compiler):
    """
    Tests against a scenario where you:

    1. Add and compile a contract
    2. Delete that contract
    3. Add a new contract with same name somewhere else

    Test such that we are able to compile successfully and not get a misleading
    collision error from deleted files.
    """
    init_contract = tmp_project.contracts_folder / "foo.__mock__"
    init_contract.write_text("LALA")
    compilers.registered_compilers[".__mock__"] = mock_compiler
    result = tmp_project.load_contracts()
    assert "foo" in result

    # Goodbye.
    init_contract.unlink()

    # Create new contract that with same name.
    new_contract = tmp_project.contracts_folder / "bar.__mock__"
    new_contract.write_text("BAZ")
    mock_compiler.overrides = {"contractName": "foo"}
    result = tmp_project.load_contracts()
    assert "foo" in result


def test_load_contracts_output_abi(tmp_project):
    cfg = {"output_extra": ["ABI"]}
    with tmp_project.temp_config(compile=cfg):
        _ = tmp_project.load_contracts()
        abi_folder = tmp_project.manifest_path.parent / "abi"
        assert abi_folder.is_dir()
        files = [x for x in abi_folder.iterdir()]
        assert len(files) > 0
        for file in files:
            assert file.suffix == ".json"


def test_manifest_path(tmp_project):
    assert tmp_project.manifest_path == tmp_project.path / ".build" / "__local__.json"


def test_clean(tmp_project):
    tmp_project.load_contracts()
    assert tmp_project.manifest_path.is_file()

    tmp_project.clean()
    assert not tmp_project.manifest_path.is_file()


def test_brownie_project_configure(config, base_projects_directory):
    project_path = base_projects_directory / "BrownieProject"
    project = BrownieProject(path=project_path, contracts_folder=Path("contracts"))
    config = project.extract_config()

    # Ensure Solidity and dependencies configuration mapped correctly
    assert config.solidity.version == "0.6.12"
    assert config.solidity.import_remapping == ["@openzeppelin/contracts=OpenZeppelin/3.1.0"]
    assert config.dependencies[0]["name"] == "OpenZeppelin"
    assert config.dependencies[0]["github"] == "OpenZeppelin/openzeppelin-contracts"
    assert config.dependencies[0]["version"] == "3.1.0"


def test_add_compiler_data(project_with_dependency_config):
    # NOTE: Using different project than default to lessen
    #   chance of race-conditions from multi-process test runners.
    project = project_with_dependency_config

    # Load contracts so that any compilers that may exist are present.
    project.load_contracts()
    start_compilers = project.manifest.compilers or []

    # NOTE: Pre-defining things to lessen chance of race condition.
    compiler = Compiler(
        name="comp",
        version="1.0.0",
        contractTypes=["foo"],
        settings={"outputSelection": {"path/to/Foo.sol": "*"}},
    )
    compiler_2 = Compiler(
        name="test",
        version="2.0.0",
        contractTypes=["bar", "stay"],
        settings={"outputSelection": {"path/to/Bar.vy": "*", "stay.vy": "*"}},
    )

    # NOTE: Has same contract as compiler 2 and thus replaces the contract.
    compiler_3 = Compiler(
        name="test",
        version="3.0.0",
        contractTypes=["bar"],
        settings={"outputSelection": {"path/to/Bar.vy": "*"}},
    )

    argument = [compiler]
    second_arg = [compiler_2]
    third_arg = [compiler_3]
    first_exp = [*start_compilers, compiler]
    final_exp = [*first_exp, compiler_2]

    # Ensure types are in manifest for type-source-id lookup.
    bar = ContractType(contractName="bar", sourceId="path/to/Bar.vy")
    foo = ContractType(contractName="foo", sourceId="path/to/Foo.sol")
    project._manifest = PackageManifest(
        contractTypes={"bar": bar, "foo": foo},
        sources={"path/to/Bar.vy": Source(), "path/to/Foo.vy": Source()},
    )
    project._contracts = project._manifest.contract_types
    assert project._manifest.contract_types, "Setup failed - need manifest contract types"

    # Add twice to show it's only added once.
    project.add_compiler_data(argument)
    project.add_compiler_data(argument)
    assert project.manifest.compilers == first_exp

    # NOTE: `add_compiler_data()` will not override existing compilers.
    #   Use `update_cache()` for that.
    project.add_compiler_data(second_arg)
    assert project.manifest.compilers == final_exp
    project.add_compiler_data(third_arg)
    comp = [c for c in project.manifest.compilers if c.name == "test" and c.version == "2.0.0"][0]
    assert "bar" not in comp.contractTypes
    assert "path/to/Bar.vy" not in comp.settings["outputSelection"]
    new_comp = [c for c in project.manifest.compilers if c.name == "test" and c.version == "3.0.0"][
        0
    ]
    assert "bar" in new_comp.contractTypes
    assert "path/to/Bar.vy" in new_comp.settings["outputSelection"]

    # Show that compilers without contract types go away.
    (compiler_3.contractTypes or []).append("stay")
    project.add_compiler_data(third_arg)
    comp_check = [
        c for c in project.manifest.compilers if c.name == "test" and c.version == "2.0.0"
    ]
    assert not comp_check

    # Show error on multiple of same compiler.
    compiler_4 = Compiler(name="test123", version="3.0.0", contractTypes=["bar"])
    compiler_5 = Compiler(name="test123", version="3.0.0", contractTypes=["baz"])
    with pytest.raises(ProjectError, match=r".*was given multiple of the same compiler.*"):
        project.add_compiler_data([compiler_4, compiler_5])

    # Show error when contract type collision (only happens with inputs, else latter replaces).
    compiler_4 = Compiler(name="test321", version="3.0.0", contractTypes=["bar"])
    compiler_5 = Compiler(name="test456", version="9.0.0", contractTypes=["bar"])
    with pytest.raises(ProjectError, match=r".*'bar' collision across compilers.*"):
        project.add_compiler_data([compiler_4, compiler_5])


def test_repr(project):
    actual = repr(project)
    # NOTE: tmp path is NOT relative to home.
    expected_project_path = str(project.path).replace(str(Path.home()), "$HOME")
    expected = f"<ProjectManager {expected_project_path}>"
    assert actual == expected
