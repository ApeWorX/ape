import json
from pathlib import Path

import pytest
from ethpm_types import Compiler, ContractType, PackageManifest, Source
from ethpm_types.manifest import PackageName
from pydantic_core import Url

from ape import Project
from ape.contracts import ContractContainer
from ape.exceptions import ProjectError
from ape.logging import LogLevel
from ape.managers.project import Dependency
from ape_pm import BrownieProject


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
def sandbox(project_path):
    real_project = Project(project_path)
    # Copies contracts and stuff into a temp folder
    # and returns a project around the temp folder.
    with real_project.sandbox() as sandbox:
        yield sandbox


@pytest.fixture
def contract_type():
    return make_contract("FooContractFromManifest")


@pytest.fixture
def manifest(contract_type):
    return make_manifest(contract_type)


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


def test_contracts_folder_deduced(sandbox):
    new_project_path = sandbox.path / "new"
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
    assert set(project.config.compile.exclude) == {"first", "second"}


def test_sandbox(project):
    # Purposely not using `sandbox` fixture.
    with project.sandbox() as sandbox:
        assert sandbox.path != project.path
        assert sandbox.is_sandbox
        # Manifest should have been created by default.
        assert not sandbox.manifest_path.is_file()


def test_is_sandbox(project, sandbox):
    assert not project.is_sandbox
    assert sandbox.is_sandbox


def test_Project(project_path):
    # Purpose not using `project_with_contracts` fixture.
    project = Project(project_path)
    project.manifest_path.unlink(missing_ok=True)
    assert project.path == project_path
    # Manifest should have been created by default.
    assert not project.manifest_path.is_file()


def test_contracts_iter(sandbox):
    actual = set(iter(sandbox.contracts))
    assert actual == {"Project", "Other"}


def test_contracts_detect_change(sandbox, ape_caplog):
    path = sandbox.contracts_folder / "Other.json"
    content = path.read_text()
    assert "foo" in content, "Test setup failed. Unexpected file content."

    # Must be compiled first.
    with ape_caplog.at_level(LogLevel.INFO):
        contracts = sandbox.load_contracts()
        assert "Other" in contracts
        ape_caplog.assert_last_log("Compiling")

        ape_caplog.clear()

        # No logs as it doesn't need to re-compile.
        sandbox.load_contracts()
        assert not ape_caplog.head

        # Make a change to the file.
        new_content = content.replace("foo", "bar")
        assert "bar" in new_content, "Test setup failed. Unexpected file content."
        path.unlink()
        path.write_text(new_content)

        # Prove re-compiles.
        contracts = sandbox.load_contracts()
        assert "Other" in contracts
        ape_caplog.assert_last_log("Compiling")


def test_getattr(sandbox):
    actual = sandbox.Other
    assert type(actual) is ContractContainer


def test_getattr_not_exists(sandbox):
    with pytest.raises(AttributeError):
        _ = sandbox.nope


def test_getattr_detects_changes(sandbox):
    source_id = sandbox.Other.contract_type.source_id
    new_abi = {
        "inputs": [],
        "name": "retrieve",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
    content = json.dumps([new_abi])
    path = sandbox.sources.lookup(source_id)
    path.unlink(missing_ok=True)
    path.write_text(content)
    # Should have re-compiled.
    contract = sandbox.Other
    assert "retrieve" in contract.contract_type.methods


def test_getattr_empty_contract(sandbox):
    """
    Tests against a condition where would infinitely compile.
    """
    source_id = sandbox.Other.contract_type.source_id
    path = sandbox.sources.lookup(source_id)
    path.unlink(missing_ok=True)
    path.write_text("")
    # Should have re-compiled.
    contract = sandbox.Other
    assert not contract.contract_type.methods


@pytest.mark.parametrize("iypthon_attr_name", ("_repr_mimebundle_", "_ipython_display_"))
def test_getattr_ipython(sandbox, iypthon_attr_name):
    # Remove contract types, if there for some reason is any.
    sandbox.manifest.contract_types = {}
    getattr(sandbox, iypthon_attr_name)
    # Prove it did not compile looking for these names.
    assert not sandbox.manifest.contract_types


def test_getattr_ipython_canary_check(sandbox):
    # Remove contract types, if there for some reason is any.
    sandbox.manifest.contract_types = {}
    with pytest.raises(AttributeError):
        getattr(sandbox, "_ipython_canary_method_should_not_exist_")

    # Prove it did not compile looking for this.
    assert not sandbox.manifest.contract_types


def test_getitem(sandbox):
    actual = sandbox["Project"]
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


def test_deployments_track_and_instance_map(sandbox, mock_sepolia, vyper_contract_instance):
    # The contract must be part of the project to track with the project manifest.
    contract_type = vyper_contract_instance.contract_type
    sandbox.manifest.contract_types = {contract_type.name: contract_type}
    sandbox.deployments.track(vyper_contract_instance)
    instance = next(iter(sandbox.deployments), None)
    assert instance is not None

    assert instance.contract_type == f"{contract_type.source_id}:{contract_type.name}"
    assert sandbox.deployments.instance_map != {}

    bip122_chain_id = sandbox.provider.get_block(0).hash.hex()
    expected_uri = f"blockchain://{bip122_chain_id[2:]}/block/"
    for key in sandbox.deployments.instance_map.keys():
        if key.startswith(expected_uri):
            return

    assert False, "Failed to find expected URI"


def test_extract_manifest(sandbox, mock_sepolia, vyper_contract_instance):
    contract_type = vyper_contract_instance.contract_type
    sandbox.manifest.contract_types = {contract_type.name: contract_type}
    sandbox.deployments.track(vyper_contract_instance)

    manifest = sandbox.extract_manifest()
    assert type(manifest) is PackageManifest
    assert manifest.meta == sandbox.meta
    assert PackageName("manifest-dependency") in (manifest.dependencies or {})
    bip122_chain_id = sandbox.provider.get_block(0).hash.hex()
    expected_uri = f"blockchain://{bip122_chain_id[2:]}"
    for key in manifest.deployments or {}:
        if key.startswith(expected_uri):
            return

    assert False, "Failed to find expected deployment URI"


def test_extract_manifest_when_sources_missing(sandbox):
    """
    Show that if a source is missing, it is OK. This happens when changing branches
    after compiling and sources are only present on one of the branches.
    """
    contract = make_contract("notreallyhere")
    sandbox.manifest.contract_types = {contract.name: contract}
    manifest = sandbox.extract_manifest()

    # Source is skipped because missing.
    assert "notreallyhere" not in manifest.contract_types


def test_exclusions(sandbox):
    exclusions = ["Other.json", "*Excl*"]
    exclude_config = {"compile": {"exclude": exclusions}}
    with sandbox.temp_config(**exclude_config):
        for exclusion in exclusions:
            assert exclusion in sandbox.exclusions


def test_sources_lookup(sandbox):
    source_id = sandbox.Other.contract_type.source_id
    path = sandbox.sources.lookup(source_id)
    assert path == sandbox.path / source_id


def test_sources_lookup_mismatched_extension(sandbox):
    source_id = sandbox.Other.contract_type.source_id
    source_id = source_id.replace(".json", ".js")
    path = sandbox.sources.lookup(source_id)
    assert path is None


def test_sources_paths_exclude(sandbox):
    exclude_config = {"compile": {"exclude": ["Other.json"]}}
    with sandbox.temp_config(**exclude_config):
        # Show default excludes also work, such as a .DS_Store file.
        ds_store = sandbox.contracts_folder / ".DS_Store"
        ds_store.write_bytes(b"asdfasf")

        # Show anything in compiler-cache is ignored.
        cache = sandbox.contracts_folder / ".cache"
        cache.mkdir(exist_ok=True)
        random_file = cache / "dontmindme.json"
        random_file.write_text("what, this isn't json?!")

        path_ids = {f"{sandbox.contracts_folder.name}/{src.name}" for src in sandbox.sources.paths}
        excluded = {".DS_Store", "Other.json", ".cache/dontmindme.json"}
        for actual in (path_ids, sandbox.sources):
            for exclusion in excluded:
                expected = f"{sandbox.contracts_folder.name}/{exclusion}"
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


def test_dependencies_iter(sandbox):
    actual = [x for x in sandbox.dependencies]
    names = [x.name for x in actual]
    assert "manifest-dependency" in names


def test_dependencies_getitem(sandbox):
    actual = sandbox.dependencies["manifest-dependency"]
    assert "local" in actual
    assert isinstance(actual["local"], Dependency)


def test_dependencies_get_dependency(sandbox):
    actual = sandbox.dependencies.get_dependency("manifest-dependency", "local")
    assert actual.name == "manifest-dependency"
    assert actual.version == "local"


def test_dependency_project(sandbox):
    dependency = sandbox.dependencies.get_dependency("renamed-contracts-folder", "local")
    project = dependency.project
    assert next(iter(project.contracts), "fail") == "renamed_contracts_folder"
    assert "renamed_contracts_folder" in project


def test_dependency_project_only_manifest(sandbox):
    """
    Shows you can use manifests as dependencies directly.
    """
    dependency = sandbox.dependencies.get_dependency("manifest-dependency", "local")
    project = dependency.project
    # Happens to also be the name of the contract.
    assert next(iter(project.contracts), "fail") == "manifest-dependency"
    assert "manifest-dependency" in project


def test_update_manifest(sandbox):
    compiler = Compiler(name="comp", version="1.0.0", contractTypes=["foo.txt"])
    sandbox.update_manifest(compilers=[compiler])
    actual = sandbox.manifest.compilers
    assert actual == [compiler]

    sandbox.update_manifest(name="test", version="1.0.0")
    assert sandbox.manifest.name == "test"
    assert sandbox.manifest.version == "1.0.0"

    # The compilers should not have changed.
    actual = sandbox.manifest.compilers
    assert actual == [compiler]


def test_load_contracts(sandbox):
    contracts = sandbox.load_contracts()
    assert sandbox.manifest_path.is_file()
    assert len(contracts) > 0
    contracts_forced = sandbox.load_contracts(use_cache=False)
    assert contracts_forced == contracts


def test_load_contracts_after_deleting_same_named_contract(sandbox, compilers, mock_compiler):
    """
    Tests against a scenario where you:

    1. Add and compile a contract
    2. Delete that contract
    3. Add a new contract with same name somewhere else

    Test such that we are able to compile successfully and not get a misleading
    collision error from deleted files.
    """
    init_contract = sandbox.contracts_folder / "foo.__mock__"
    init_contract.write_text("LALA")
    compilers.registered_compilers[".__mock__"] = mock_compiler
    result = sandbox.load_contracts()
    assert "foo" in result

    # Goodbye.
    init_contract.unlink()

    # Create new contract that with same name.
    new_contract = sandbox.contracts_folder / "bar.__mock__"
    new_contract.write_text("BAZ")
    mock_compiler.overrides = {"contractName": "foo"}
    result = sandbox.load_contracts()
    assert "foo" in result


def test_manifest_path(sandbox):
    assert sandbox.manifest_path == sandbox.path / ".build" / "__local__.json"


def test_clean(sandbox):
    sandbox.load_contracts()
    assert sandbox.manifest_path.is_file()

    sandbox.clean()
    assert not sandbox.manifest_path.is_file()


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
    compiler = Compiler(name="comp", version="1.0.0", contractTypes=["foo"])
    compiler_2 = Compiler(name="test", version="2.0.0", contractTypes=["bar", "stay"])

    # NOTE: Has same contract as compiler 2 and thus replaces the contract.
    compiler_3 = Compiler(name="test", version="3.0.0", contractTypes=["bar"])

    argument = [compiler]
    second_arg = [compiler_2]
    third_arg = [compiler_3]
    first_exp = [*start_compilers, compiler]
    final_exp = [*first_exp, compiler_2]

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
