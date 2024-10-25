import json
import os
import re
import shutil
from pathlib import Path

import pytest
from eth_utils import to_hex
from ethpm_types import Compiler, ContractType, PackageManifest, Source
from ethpm_types.manifest import PackageName
from pydantic_core import Url

import ape
from ape import Project
from ape.api.projects import ApeProject
from ape.contracts import ContractContainer
from ape.exceptions import ConfigError, ProjectError
from ape.logging import LogLevel
from ape.utils import create_tempdir
from ape_pm.project import BrownieProject, FoundryProject
from tests.conftest import skip_if_plugin_installed


@pytest.fixture
def tmp_project(with_dependencies_project_path):
    real_project = Project(with_dependencies_project_path)
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
    return to_hex(eth_tester_provider.get_block(block_number).hash)


@pytest.fixture
def project_from_manifest(manifest):
    return Project.from_manifest(manifest)


@pytest.fixture(scope="module")
def foundry_toml():
    return """
[profile.default]
src = 'src'
out = 'out'
libs = ['lib']
solc = "0.8.18"
evm_version = 'cancun'

remappings = [
    'forge-std/=lib/forge-std/src/',
    '@openzeppelin/=lib/openzeppelin-contracts/',
]
""".lstrip()


def make_contract(name: str = "test") -> ContractType:
    return ContractType.model_validate(
        {
            "contractName": name,
            "sourceId": f"contracts/{name}.json",
            "abi": [],
        }
    )


def make_manifest(*contracts: ContractType, include_contract_type: bool = True) -> PackageManifest:
    sources = {
        ct.source_id: Source(content=ct.model_dump_json(by_alias=True, mode="json"))
        for ct in contracts
    }
    model: dict = {"sources": sources}
    if include_contract_type:
        contract_types = {c.name: c for c in contracts}
        model["contractTypes"] = contract_types

    return PackageManifest.model_validate(model)


def test_path(project):
    assert project.path is not None


def test_path_configured(project):
    """
    Simulating package structures like snekmate.
    """
    madeup_name = "snakemate"
    with create_tempdir(name=madeup_name) as temp_dir:
        subdir = temp_dir / "src"
        contracts_folder = subdir / madeup_name
        contracts_folder.mkdir(parents=True)
        contract = contracts_folder / "snake.json"
        abi = [{"name": "foo", "type": "fallback", "stateMutability": "nonpayable"}]
        contract.write_text(json.dumps(abi), encoding="utf8")

        snakemate = Project(
            temp_dir, config_override={"base_path": "src", "contracts_folder": madeup_name}
        )
        assert snakemate.name == madeup_name
        assert snakemate.path == subdir
        assert snakemate.contracts_folder == contracts_folder

        # The repr should show `/snakemate` and not `/snakemate/src/`.
        assert re.match(r"<ProjectManager [\w|/]*/snakemate>", repr(snakemate))

        actual = snakemate.load_contracts()
        assert "snake" in actual
        assert actual["snake"].source_id == f"{madeup_name}/snake.json"


def test_name(project):
    assert project.name == project.path.name


def test_name_from_config(project):
    with project.temp_config(name="foo-bar"):
        assert project.name == "foo-bar"


def test_repr(project):
    actual = repr(project)
    # NOTE: tmp path is NOT relative to home.
    expected_project_path = str(project.path).replace(str(Path.home()), "$HOME")
    expected = f"<ProjectManager {expected_project_path}>"
    assert actual == expected


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
    contract.write_text(json.dumps(abi), encoding="utf8")
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


def test_isolate_in_tempdir_does_not_alter_sources(project):
    # First, create a bad source.
    with project.temp_config(contracts_folder="tests"):
        new_src = project.contracts_folder / "newsource.json"
        new_src.write_text("this is not json, oops")
        project.sources.refresh()  # Only need to be called when run with other tests.

        try:
            with project.isolate_in_tempdir() as tmp_project:
                # The new (bad) source should be in the temp project.
                actual = {**(tmp_project.manifest.sources or {})}
        finally:
            new_src.unlink()
            project.sources.refresh()

        # Ensure "newsource" did not persist in the in-memory manifest.
        assert "tests/newsource.json" in actual, project.path
        assert "tests/newsource.json" not in (project.manifest.sources or {})


def test_in_tempdir(project, tmp_project):
    assert not project.in_tempdir
    assert tmp_project.in_tempdir


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
    path.write_text(content, encoding="utf8")
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
    path.write_text("", encoding="utf8")
    # Should have re-compiled.
    contract = tmp_project.Other
    assert not contract.contract_type.methods


@skip_if_plugin_installed("vyper", "solidity")
def test_getattr_same_name_as_source_file(project_with_source_files_contract):
    expected = (
        r"'LocalProject' object has no attribute 'ContractA'\. "
        r"Also checked extra\(s\) 'contracts'\. "
        r"However, there is a source file named 'ContractA\.sol'\. "
        r"This file may not be compiling \(see error above\), "
        r"or maybe you meant to reference a contract name from this source file\? "
        r"Else, could it be from one of the missing compilers for extensions: .*"
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


def test_extract_manifest(tmp_project, mock_sepolia, vyper_contract_instance):
    contract_type = vyper_contract_instance.contract_type
    tmp_project.manifest.contract_types = {contract_type.name: contract_type}
    tmp_project.deployments.track(vyper_contract_instance)

    manifest = tmp_project.extract_manifest()
    assert type(manifest) is PackageManifest
    assert manifest.meta == tmp_project.meta
    assert PackageName("manifest-dependency") in (manifest.dependencies or {})
    bip122_chain_id = to_hex(tmp_project.provider.get_block(0).hash)
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


def test_extract_manifest_excludes_cache(tmp_project):
    cachefile = tmp_project.contracts_folder / ".cache" / "CacheFile.json"
    cachefile2 = tmp_project.contracts_folder / ".cache" / "subdir" / "Cache2.json"
    cachefile2.parent.mkdir(parents=True)
    cachefile.write_text("Doesn't matter", encoding="utf8")
    cachefile2.write_text("Doesn't matter", encoding="utf8")
    manifest = tmp_project.extract_manifest()
    assert isinstance(manifest, PackageManifest)
    assert ".cache/CacheFile.json" not in (manifest.sources or {})
    assert ".cache/subdir/CacheFile.json" not in (manifest.sources or {})


def test_extract_manifest_compiles(tmp_project):
    tmp_project.manifest.contract_types = {}  # Not compiled.
    actual = tmp_project.extract_manifest()
    assert actual.contract_types  # Fails if empty


def test_extract_manifest_from_manifest_project(project_from_manifest):
    project_from_manifest.manifest.contract_types = {}  # Not compiled.
    manifest = project_from_manifest.extract_manifest()
    assert "FooContractFromManifest" in manifest.contract_types


def test_exclusions(tmp_project):
    exclusions = ["Other.json", "*Excl*"]
    exclude_config = {"compile": {"exclude": exclusions}}
    with tmp_project.temp_config(**exclude_config):
        for exclusion in exclusions:
            assert exclusion in tmp_project.exclusions


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

    # Delete a file and ensure it is does not show up in dict.
    contract_to_rm = next(iter(contracts.values()))
    (tmp_project.path / contract_to_rm.source_id).unlink()
    contracts = tmp_project.load_contracts()
    assert contract_to_rm.name not in contracts


def test_load_contracts_detect_change(tmp_project, ape_caplog):
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
        path.write_text(new_content, encoding="utf8")

        # Prove re-compiles.
        contracts = tmp_project.load_contracts()
        assert "Other" in contracts
        ape_caplog.assert_last_log("Compiling")


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
    init_contract.write_text("LALA", encoding="utf8")
    compilers.registered_compilers[".__mock__"] = mock_compiler
    result = tmp_project.load_contracts()
    assert "foo" in result

    # Goodbye.
    init_contract.unlink()

    # Since we are changing files mid-session, we need to refresh the project.
    # Typically, users don't have to do this.
    tmp_project.refresh_sources()

    result = tmp_project.load_contracts()
    assert "foo" not in result  # Was deleted.
    # Also ensure it is gone from paths.
    assert "foo.__mock__" not in [x.name for x in tmp_project.sources.paths]

    # Create a new contract with the same name.
    new_contract = tmp_project.contracts_folder / "bar.__mock__"
    new_contract.write_text("BAZ", encoding="utf8")
    tmp_project.refresh_sources()

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

        # Ensure is usable.
        data = json.loads(file.read_text(encoding="utf8"))
        assert isinstance(data, list)
        assert len(data) >= 1
        # There was bug where this was a str.
        assert isinstance(data[0], dict)


def test_load_contracts_use_cache(mocker, tmp_project):
    """
    Showing the 'use_cache=bool' kwarg works.
    """
    compile_spy = mocker.spy(tmp_project.contracts, "_compile")

    tmp_project.manifest.contract_types = {}  # Force initial compile.
    contracts = tmp_project.load_contracts(use_cache=True)
    assert "Other" in contracts  # Other.json contract.
    assert "Project" in contracts  # Project.json contract.
    assert compile_spy.call_args_list[-1][-1]["use_cache"] is True

    # Show they get added to the manifest.
    assert "Other" in tmp_project.manifest.contract_types
    assert "Project" in tmp_project.manifest.contract_types

    # Showe we can use the cache again (no compiling!)
    contracts = tmp_project.load_contracts(use_cache=True)
    assert "Other" in contracts  # Other.json contract.
    assert "Project" in contracts  # Project.json contract.
    assert compile_spy.call_args_list[-1][-1]["use_cache"] is True

    # Show force-recompiles.
    contracts = tmp_project.load_contracts(use_cache=False)
    assert "Other" in contracts  # Other.json contract.
    assert "Project" in contracts  # Project.json contract.
    assert compile_spy.call_args_list[-1][-1]["use_cache"] is False


def test_manifest_path(tmp_project):
    assert tmp_project.manifest_path == tmp_project.path / ".build" / "__local__.json"


def test_clean(tmp_project):
    tmp_project.load_contracts()
    assert tmp_project.manifest_path.is_file()

    tmp_project.clean()
    assert not tmp_project.manifest_path.is_file()
    assert tmp_project._manifest.contract_types is None
    assert tmp_project.sources._path_cache is None


def test_unpack(project_with_source_files_contract):
    with create_tempdir() as path:
        project_with_source_files_contract.unpack(path)
        assert (path / "contracts" / "Contract.json").is_file()

        # Show that even non-sources end up in the unpacked destination.
        assert (path / "contracts" / "Path.with.sub.json").is_file()


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


def test_project_api_foundry_and_ape_config_found(foundry_toml):
    """
    If a project is both a Foundry project and an Ape project,
    ensure Ape treats it as an Ape project.
    """
    with ape.Project.create_temporary_project() as temp_project:
        foundry_cfg_file = temp_project.path / "foundry.toml"
        foundry_cfg_file.write_text(foundry_toml, encoding="utf8")

        ape_cfg_file = temp_project.path / "ape-config.yaml"
        ape_cfg_file.write_text("name: testfootestfootestfoo", encoding="utf8")

        actual = temp_project.project_api
        assert isinstance(actual, ApeProject)
        assert not isinstance(actual, FoundryProject)


def test_get_contract(project_with_contracts):
    actual = project_with_contracts.get_contract("Other")
    assert isinstance(actual, ContractContainer), f"{type(actual)}"
    assert actual.contract_type.name == "Other"

    # Ensure manifest is only loaded once by none-ing out the path.
    # Otherwise, this can be a MAJOR performance hit.
    manifest_path = project_with_contracts.manifest_path
    project_with_contracts.manifest_path = None
    try:
        actual = project_with_contracts.get_contract("Other")
        assert isinstance(actual, ContractContainer)
        assert actual.contract_type.name == "Other"
    finally:
        project_with_contracts.manifest_path = manifest_path


def test_get_contract_not_exists(project):
    actual = project.get_contract("this is not a contract")
    assert actual is None


class TestProject:
    """
    All tests related to ``ape.Project``.
    """

    def test_init(self, with_dependencies_project_path):
        # Purpose not using `project_with_contracts` fixture.
        project = Project(with_dependencies_project_path)
        project.manifest_path.unlink(missing_ok=True)
        assert project.path == with_dependencies_project_path
        # Manifest should have been created by default.
        assert not project.manifest_path.is_file()

    def test_init_invalid_config(self):
        here = os.curdir
        with create_tempdir() as temp_dir:
            cfgfile = temp_dir / "ape-config.yaml"
            # Name is invalid!
            cfgfile.write_text("name:\n  {asdf}")

            os.chdir(temp_dir)
            expected = r"[.\n]*Input should be a valid string\n-->1: name:\n   2:   {asdf}[.\n]*"
            try:
                with pytest.raises(ConfigError, match=expected):
                    _ = Project(temp_dir)
            finally:
                os.chdir(here)

    def test_config_override(self, with_dependencies_project_path):
        contracts_folder = with_dependencies_project_path / "my_contracts"
        config = {"contracts_folder": contracts_folder.name}
        project = Project(with_dependencies_project_path, config_override=config)
        assert project.contracts_folder == contracts_folder

    def test_from_manifest(self, manifest):
        # Purposely not using `project_from_manifest` fixture.
        project = Project.from_manifest(manifest)
        assert isinstance(project, Project)
        assert project.manifest == manifest

    def test_from_manifest_contracts_iter(self, contract_type, project_from_manifest):
        actual = set(iter(project_from_manifest.contracts))
        assert actual == {"FooContractFromManifest"}

    def test_from_manifest_getattr(self, contract_type, project_from_manifest):
        expected = ContractContainer(contract_type)
        actual = project_from_manifest.FooContractFromManifest
        assert isinstance(actual, ContractContainer)
        assert actual == expected

    def test_from_manifest_getitem(self, contract_type, project_from_manifest):
        expected = ContractContainer(contract_type)
        assert project_from_manifest["FooContractFromManifest"] == expected

    def test_from_manifest_load_contracts(self, contract_type):
        """
        Show if contract-types are missing but sources set,
        compiling will add contract-types.
        """
        manifest = make_manifest(contract_type, include_contract_type=False)
        project = Project.from_manifest(manifest)
        assert not project.manifest.contract_types, "Setup failed"

        # Returns containers, not types.
        actual = project.load_contracts()
        assert actual[contract_type.name].contract_type == contract_type

        # Also, show it got set on the manifest.
        assert project.manifest.contract_types == {contract_type.name: contract_type}

    def test_from_python_library(self):
        # web3py as an ape-project dependency.
        web3 = Project.from_python_library("web3")
        assert "site-packages" in str(web3.path)
        assert web3.path.name == "web3"

    def test_hash(self, with_dependencies_project_path, project_from_manifest):
        """
        Show we can use projects in sets.
        """
        project_0 = Project(with_dependencies_project_path)
        project_1 = Project.from_python_library("web3")
        project_2 = project_from_manifest

        # Show we can use in sets.
        project_set = {project_0, project_1, project_2}
        assert len(project_set) == 3

        # Show we can use as dict-keys:
        project_dict = {project_0: 123}
        assert project_dict[project_0] == 123


class TestBrownieProject:
    """
    Tests related to the brownie implementation of the ProjectAPI.
    """

    @pytest.fixture
    def brownie_project(self, base_projects_directory):
        project_path = base_projects_directory / "BrownieProject"
        return BrownieProject(path=project_path)

    def test_extract_config(self, config, brownie_project):
        config = brownie_project.extract_config()

        # Ensure contracts_folder works.
        assert config.contracts_folder == "contractsrenamed"

        # Ensure Solidity and dependencies configuration mapped correctly
        assert config.solidity.version == "0.6.12"

        # NOTE: `contracts/` is not part of the import key as it is
        # usually included in the import statements.
        assert [str(x) for x in config.solidity.import_remapping] == [
            "@openzeppelin=openzeppelin/3.1.0"
        ]
        assert config.dependencies[0]["name"] == "openzeppelin"
        assert config.dependencies[0]["github"] == "OpenZeppelin/openzeppelin-contracts"
        assert config.dependencies[0]["version"] == "3.1.0"


class TestFoundryProject:
    @pytest.fixture
    def mock_github(self, mocker):
        return mocker.MagicMock()

    @pytest.fixture(scope="class")
    def gitmodules(self):
        return """
[submodule "lib/forge-std"]
    path = lib/forge-std
    url = https://github.com/foundry-rs/forge-std
    branch = v1.5.2
[submodule "lib/openzeppelin-contracts"]
    path = lib/openzeppelin-contracts
    url = https://github.com/OpenZeppelin/openzeppelin-contracts
    release = v4.9.5
    branch = v4.9.5
[submodule "lib/erc4626-tests"]
    path = lib/erc4626-tests
    url = https://github.com/a16z/erc4626-tests.git
""".lstrip().replace(
            "    ", "\t"
        )

    def test_extract_config(self, foundry_toml, gitmodules, mock_github):
        with create_tempdir() as temp_dir:
            cfg_file = temp_dir / "foundry.toml"
            cfg_file.write_text(foundry_toml, encoding="utf8")
            gitmodules_file = temp_dir / ".gitmodules"
            gitmodules_file.write_text(gitmodules, encoding="utf8")
            temp_project = Project(temp_dir)

            api = temp_project.project_api
            mock_github.get_repo.return_value = {"default_branch": "main"}
            api._github_client = mock_github  # type: ignore
            assert isinstance(api, FoundryProject)

            # Ensure solidity config migrated.
            actual = temp_project.config.model_dump(
                by_alias=True
            )  # Is result of ``api.extract_config()``.
            assert actual["contracts_folder"] == "src"
            assert "solidity" in actual, "Solidity failed to migrate"
            actual_sol = actual["solidity"]
            assert actual_sol["import_remapping"] == [
                "@openzeppelin=src/.cache/openzeppelin/v4.9.5/",
                "forge-std=src/.cache/forge-std/v1.5.2/src",
            ]
            assert actual_sol["version"] == "0.8.18"
            assert actual_sol["evm_version"] == "cancun"

            # Ensure dependencies migrated from .gitmodules.
            assert "dependencies" in actual, "Dependencies failed to migrate"
            actual_dependencies = actual["dependencies"]
            expected_dependencies = [
                {"github": "foundry-rs/forge-std", "name": "forge-std", "ref": "v1.5.2"},
                {
                    "github": "OpenZeppelin/openzeppelin-contracts",
                    "name": "openzeppelin",
                    "version": "v4.9.5",
                },
                {"github": "a16z/erc4626-tests", "name": "erc4626-tests", "ref": "main"},
            ]
            assert actual_dependencies == expected_dependencies


class TestSourceManager:
    def test_lookup(self, tmp_project):
        source_id = tmp_project.Other.contract_type.source_id
        path = tmp_project.sources.lookup(source_id)
        assert path == tmp_project.path / source_id

    def test_lookup_missing_extension(self, tmp_project):
        source_id = tmp_project.Other.contract_type.source_id
        source_id_wo_ext = ".".join(source_id.split(".")[:-1])
        path = tmp_project.sources.lookup(source_id_wo_ext)
        assert path == tmp_project.path / source_id

    def test_lookup_mismatched_extension(self, tmp_project):
        source_id = tmp_project.Other.contract_type.source_id
        source_id = source_id.replace(".json", ".js")
        path = tmp_project.sources.lookup(source_id)
        assert path is None

    def test_lookup_closest_match(self, project_with_source_files_contract):
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
                nested_src.write_text(source_path.read_text(), encoding="utf8")

            # Top-level match.
            for base in (source_path, str(source_path), "Contract", "Contract.json"):
                # Using stem in case it returns `Contract.__mock__`, which is
                # added / removed as part of other tests (running x-dist).
                assert pm.sources.lookup(base).stem == source_path.stem, f"Failed to lookup {base}"

            # Nested: 1st level
            for closest in (
                nested_source_a,
                str(nested_source_a),
                "temp/Contract",
                "temp/Contract.json",
            ):
                actual = pm.sources.lookup(closest)
                expected = nested_source_a
                # Using stem in case it returns `Contract.__mock__`, which is
                # added / removed as part of other tests (running x-dist).
                assert actual.stem == expected.stem, f"Failed to lookup {closest}"

            # Nested: 2nd level
            for closest in (
                nested_source_b,
                str(nested_source_b),
                "temp/tempb/Contract",
                "temp/tempb/Contract.json",
            ):
                actual = pm.sources.lookup(closest)
                expected = nested_source_b

                # Using stem in case it returns `Contract.__mock__`, which is
                # added / removed as part of other tests (running x-dist).
                assert actual.stem == expected.stem, f"Failed to lookup {closest}"

        finally:
            clean()

    def test_lookup_not_found(self, tmp_project):
        assert tmp_project.sources.lookup("madeup.json") is None

    def test_lookup_missing_contracts_prefix(self, project_with_source_files_contract):
        """
        Show we can exclude the `contracts/` prefix in a source ID.
        """
        project = project_with_source_files_contract
        actual_from_str = project.sources.lookup("ContractA.sol")
        actual_from_path = project.sources.lookup(Path("ContractA.sol"))
        expected = project.contracts_folder / "ContractA.sol"
        assert actual_from_str == actual_from_path == expected
        assert actual_from_str.is_absolute()
        assert actual_from_path.is_absolute()

    def test_paths_exclude(self, tmp_project):
        exclude_config = {"compile": {"exclude": ["Other.json"]}}
        with tmp_project.temp_config(**exclude_config):
            # Show default excludes also work, such as a .DS_Store file.
            ds_store = tmp_project.contracts_folder / ".DS_Store"
            ds_store.write_bytes(b"asdfasf")

            # Show anything in compiler-cache is ignored.
            cache = tmp_project.contracts_folder / ".cache"
            cache.mkdir(exist_ok=True)
            random_file = cache / "dontmindme.json"
            random_file.write_text("what, this isn't json?!", encoding="utf8")

            path_ids = {
                f"{tmp_project.contracts_folder.name}/{src.name}"
                for src in tmp_project.sources.paths
            }
            excluded = {".DS_Store", "Other.json", ".cache/dontmindme.json"}
            for actual in (path_ids, tmp_project.sources):
                for exclusion in excluded:
                    expected = f"{tmp_project.contracts_folder.name}/{exclusion}"
                    assert expected not in actual

    def test_is_excluded(self, project_with_contracts):
        exclude_cfg = {"compile": {"exclude": ["exclude_dir/*", "Excl*.json"]}}
        source_ids = ("contracts/exclude_dir/UnwantedContract.json", "contracts/Exclude.json")
        with project_with_contracts.temp_config(**exclude_cfg):
            for source_id in source_ids:
                path = project_with_contracts.path / source_id
                assert project_with_contracts.sources.is_excluded(path)

    def test_items(self, project_with_contracts):
        actual = list(project_with_contracts.sources.items())
        assert len(actual) > 0
        assert isinstance(actual[0], tuple)
        assert "contracts/Other.json" in [x[0] for x in actual]
        assert isinstance(actual[0][1], Source)

    def test_keys(self, project_with_contracts):
        actual = list(project_with_contracts.sources.keys())
        assert "contracts/Other.json" in actual

    def test_values(self, project_with_contracts):
        actual = list(project_with_contracts.sources.values())
        assert all(isinstance(x, Source) for x in actual)


class TestContractManager:
    def test_iter(self, tmp_project):
        actual = set(iter(tmp_project.contracts))
        assert actual == {"Project", "Other"}

    def test_compile(self, tmp_project):
        actual = list(tmp_project.contracts._compile("contracts/Project.json"))
        assert len(actual) == 1
        assert actual[0].contract_type.name == "Project"

        # Show it can happen again.
        actual = list(tmp_project.contracts._compile("contracts/Project.json"))
        assert len(actual) == 1
        assert actual[0].contract_type.name == "Project"

    def test_values(self, tmp_project):
        contracts = [c for c in tmp_project.contracts.values()]
        actual = {x.name for x in contracts}
        assert len(actual) == 2
        assert actual == {"Other", "Project"}
        # Delete a file and try again, as a test.
        file = tmp_project.path / contracts[0].source_id
        file.unlink()

        contracts = [c for c in tmp_project.contracts.values()]
        actual = {x.name for x in contracts}
        assert len(actual) == 1
        assert file.name not in actual


class TestDeploymentManager:
    @pytest.fixture
    def project(self, tmp_project, vyper_contract_instance, mock_sepolia):
        contract_type = vyper_contract_instance.contract_type
        tmp_project.manifest.contract_types = {contract_type.name: contract_type}
        return tmp_project

    def test_track(self, project, vyper_contract_instance, mock_sepolia):
        project.deployments.track(vyper_contract_instance)
        deployment = next(iter(project.deployments), None)
        contract_type = vyper_contract_instance.contract_type
        assert deployment is not None
        assert deployment.contract_type == f"{contract_type.source_id}:{contract_type.name}"

    def test_instance_map(self, project, vyper_contract_instance, mock_sepolia):
        project.deployments.track(vyper_contract_instance)
        assert project.deployments.instance_map != {}

        bip122_chain_id = to_hex(project.provider.get_block(0).hash)
        expected_uri = f"blockchain://{bip122_chain_id[2:]}/block/"
        for key in project.deployments.instance_map.keys():
            if key.startswith(expected_uri):
                return

        assert False, "Failed to find expected URI"
