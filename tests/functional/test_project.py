import json
import os
import re
import shutil
from pathlib import Path

import pytest
from eth_utils import to_hex
from ethpm_types import Compiler, ContractType, PackageManifest, Source

from ape import Project
from ape.contracts import ContractContainer
from ape.exceptions import ConfigError, ProjectError
from ape.logging import LogLevel
from ape.managers.project import MultiProject
from ape.utils import create_tempdir
from ape_pm.project import BrownieProject, FoundryProject


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


@pytest.fixture
def tmp_project(project):
    with project.isolate_in_tempdir() as tmp_project:
        yield tmp_project


@pytest.fixture(scope="module")
def foundry_toml():
    return """
[profile.default]
src = 'src'
out = 'out'
libs = ['lib']
solc = "0.8.18"
evm_version = 'cancun'
via_ir = true

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


def test_path(smaller_project):
    assert smaller_project.path is not None


def test_path_configured():
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


def test_name(smaller_project):
    assert smaller_project.name == smaller_project.path.name


def test_name_from_config(project):
    with project.temp_config(name="foo-bar"):
        assert project.name == "foo-bar"


def test_repr():
    with create_tempdir() as tmpdir:
        project = Project(tmpdir)
        actual = repr(project)

    expected = f"<ProjectManager {tmpdir}>"
    assert actual == expected


@pytest.mark.parametrize("name", ("contracts", "contracts"))
def test_contracts_folder_from_config(smaller_project, name):
    with smaller_project.temp_config(contracts_folder=name):
        assert smaller_project.contracts_folder == smaller_project.path / name


def test_contracts_folder_same_as_root_path(smaller_project):
    with smaller_project.temp_config(contracts_folder="."):
        assert smaller_project.contracts_folder == smaller_project.path


def test_contracts_folder_deduced(tmp_project):
    new_project_path = tmp_project.path / "new"
    new_project_path.mkdir()
    contracts_folder = new_project_path / "contracts"
    contracts_folder.mkdir()
    contract = contracts_folder / "tryme.json"
    abi = [{"name": "foo", "type": "fallback", "stateMutability": "nonpayable"}]
    contract.write_text(json.dumps(abi), encoding="utf8")
    new_project = Project(new_project_path)
    actual = new_project.contracts_folder
    assert actual == contracts_folder


def test_reconfigure(small_temp_project):
    small_temp_project.reconfigure(compile={"exclude": ["first", "second"]})
    assert {"first", "second"}.issubset(set(small_temp_project.config.compile.exclude))


def test_isolate_in_tempdir(smaller_project):
    with smaller_project.isolate_in_tempdir() as tmp_project:
        assert tmp_project.path != smaller_project.path
        assert tmp_project.in_tempdir


def test_isolate_in_tempdir_does_not_alter_sources(smaller_project):
    # First, create a bad source.
    with smaller_project.temp_config(contracts_folder="build"):
        new_src = smaller_project.contracts_folder / "newsource.json"
        new_src.parent.mkdir(exist_ok=True, parents=True)
        new_src.write_text("this is not json, oops")
        smaller_project.sources.refresh()  # Only need to be called when run with other tests.

        try:
            with smaller_project.isolate_in_tempdir() as tmp_project:
                # The new (bad) source should be in the temp project.
                actual = {**(tmp_project.manifest.sources or {})}
        finally:
            new_src.unlink()
            smaller_project.sources.refresh()

        # Ensure "newsource" did not persist in the in-memory manifest.
        assert "build/newsource.json" in actual
        assert "build/newsource.json" not in (smaller_project.manifest.sources or {})


def test_in_tempdir(smaller_project):
    assert not Project(Path(__file__).parent).in_tempdir
    with smaller_project.isolate_in_tempdir() as tmp_project:
        assert tmp_project.in_tempdir


def test_getattr(smaller_project):
    actual = smaller_project.Other
    assert type(actual) is ContractContainer


def test_getattr_not_exists(smaller_project):
    expected = (
        r"'LocalProject' object has no attribute 'nope'\. Also checked extra\(s\) 'contracts'\."
    )
    with pytest.raises(AttributeError, match=expected) as err:
        _ = smaller_project.nope

    # Was the case where the last entry was from Ape's basemodel stuff.
    # Now, it points at the project manager last.
    assert "ape/managers/project.py:" in repr(err.traceback[-1])


def test_getattr_detects_changes(small_temp_project):
    # For this test, ensure we use a JSON/ABI contract so it is easier
    # to change its contents.
    source_id = small_temp_project.Other.contract_type.source_id
    new_abi = {
        "inputs": [],
        "name": "retrieve",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    }
    content = json.dumps([new_abi])
    path = small_temp_project.sources.lookup(source_id)
    assert path

    path.unlink(missing_ok=True)
    path.write_text(content, encoding="utf8")
    # Should have re-compiled.
    contract = small_temp_project.Other
    assert "retrieve" in contract.contract_type.methods


def test_getattr_empty_contract(small_temp_project):
    """
    Tests against a condition where would infinitely compile.
    """
    source_id = small_temp_project.Other.contract_type.source_id
    path = small_temp_project.sources.lookup(source_id)
    path.unlink(missing_ok=True)
    path.write_text("", encoding="utf8")
    # Should have re-compiled.
    contract = small_temp_project.Other
    assert not contract.contract_type.methods


def test_getattr_same_name_as_source_file(small_temp_project):
    new_file = small_temp_project.contracts_folder / "NewContract.sol"
    content = """
    // SPDX-License-Identifier: LGPL-3.0-only
    pragma solidity >=0.7.0 <0.8.0;
    contract DifferentName {}
    """
    new_file.write_text(content, encoding="utf8")
    expected = (
        r"'LocalProject' object has no attribute 'NewContract'\. "
        r"Also checked extra\(s\) 'contracts'\. "
        r"However, there is a source file named 'NewContract\.sol'\. "
        r"This file may not be compiling \(see error above\), "
        r"or maybe you meant to reference a contract name from this source file\?*"
    )
    with pytest.raises(AttributeError, match=expected):
        _ = small_temp_project.NewContract


@pytest.mark.parametrize("iypthon_attr_name", ("_repr_mimebundle_", "_ipython_display_"))
def test_getattr_ipython(smaller_project, iypthon_attr_name):
    # Remove contract types, if there is any.
    smaller_project.manifest.contract_types = {}
    getattr(smaller_project, iypthon_attr_name)
    # Prove it did not compile looking for these names.
    assert not smaller_project.manifest.contract_types


def test_getattr_ipython_canary_check(tmp_project):
    tmp_project.manifest.contract_types = {}

    with pytest.raises(AttributeError):
        _ = tmp_project._ipython_canary_method_should_not_exist_

    assert not tmp_project.manifest.contract_types  # Didn't compile


def test_getitem(smaller_project):
    actual = smaller_project["Other"]
    assert type(actual) is ContractContainer


def test_meta(smaller_project):
    meta_config = {
        "meta": {
            "authors": ["Apealicious Jones"],
            "license": "MIT",
            "description": "Zoologist meme protocol",
            "keywords": ["Indiana", "Knight's Templar"],
            "links": {"apeworx.io": "https://apeworx.io"},
        }
    }
    with smaller_project.temp_config(**meta_config):
        assert smaller_project.meta.authors == ["Apealicious Jones"]
        assert smaller_project.meta.license == "MIT"
        assert smaller_project.meta.description == "Zoologist meme protocol"
        assert smaller_project.meta.keywords == ["Indiana", "Knight's Templar"]
        assert len(smaller_project.meta.links) == 1
        assert f"{smaller_project.meta.links['apeworx.io']}" == "https://apeworx.io/"


def test_extract_manifest(smaller_project, vyper_contract_instance):
    contract_type = vyper_contract_instance.contract_type
    smaller_project.manifest.contract_types = {contract_type.name: contract_type}
    smaller_project.deployments.track(vyper_contract_instance, allow_dev=True)

    manifest = smaller_project.extract_manifest()
    assert type(manifest) is PackageManifest
    assert manifest.meta == smaller_project.meta
    assert "manifest-dependency" in (manifest.dependencies or {})
    bip122_chain_id = to_hex(smaller_project.provider.get_block(0).hash)
    expected_uri = f"blockchain://{bip122_chain_id[2:]}"
    for key in manifest.deployments or {}:
        if key.startswith(expected_uri):
            return

    assert False, "Failed to find expected deployment URI"


def test_extract_manifest_when_sources_missing(empty_project):
    """
    Show that if a source is missing, it is OK. This happens when changing branches
    after compiling and contracts are only present on one of the branches.
    """
    contract = make_contract("notreallyhere")
    empty_project.manifest.contract_types = {contract.name: contract}
    manifest = empty_project.extract_manifest()

    # Source is skipped because missing.
    assert "notreallyhere" not in manifest.contract_types


def test_extract_manifest_excludes_cache(empty_project):
    cachefile = empty_project.contracts_folder / ".cache" / "CacheFile.json"
    cachefile2 = empty_project.contracts_folder / ".cache" / "subdir" / "Cache2.json"
    cachefile2.parent.mkdir(parents=True)
    cachefile.write_text("Doesn't matter", encoding="utf8")
    cachefile2.write_text("Doesn't matter", encoding="utf8")
    manifest = empty_project.extract_manifest()
    assert isinstance(manifest, PackageManifest)
    assert ".cache/CacheFile.json" not in (manifest.sources or {})
    assert ".cache/subdir/CacheFile.json" not in (manifest.sources or {})


def test_extract_manifest_compiles(smaller_project):
    smaller_project.manifest.contract_types = {}  # Not compiled.
    actual = smaller_project.extract_manifest()
    assert actual.contract_types  # Fails if empty


def test_extract_manifest_from_manifest_project(project_from_manifest):
    project_from_manifest.manifest.contract_types = {}  # Not compiled.
    manifest = project_from_manifest.extract_manifest()
    assert "FooContractFromManifest" in manifest.contract_types


def test_exclusions(smaller_project):
    exclusions = ["Other.json", "*Excl*"]
    exclude_config = {"compile": {"exclude": exclusions}}
    with smaller_project.temp_config(**exclude_config):
        for exclusion in exclusions:
            assert exclusion in smaller_project.exclusions


def test_update_manifest(empty_project):
    compiler = Compiler(name="comp", version="1.0.0", contractTypes=["foo.txt"])
    empty_project.update_manifest(compilers=[compiler])
    actual = empty_project.manifest.compilers
    assert actual == [compiler]

    empty_project.update_manifest(name="test", version="1.0.0")
    assert empty_project.manifest.name == "test"
    assert empty_project.manifest.version == "1.0.0"

    # The compilers should not have changed.
    actual = empty_project.manifest.compilers
    assert actual == [compiler]


def test_load_contracts(small_temp_project):
    contracts = small_temp_project.load_contracts()
    assert small_temp_project.manifest_path.is_file()
    assert len(contracts) > 0
    contracts_forced = small_temp_project.load_contracts(use_cache=False)
    assert len(contracts_forced) > 0

    # Delete a file and ensure it does not show up in dict.
    try:
        contract_to_rm = small_temp_project.contracts["Other"]
    except KeyError:
        existing_contracts = ",".join([k for k in small_temp_project.contracts.keys()])
        pytest.fail(f"Contract named 'Other' not found. Existing contracts: {existing_contracts}")
        return

    contract_path = small_temp_project.sources.lookup(contract_to_rm.source_id)
    contract_path.unlink()
    contracts = small_temp_project.load_contracts()
    assert contract_to_rm.name not in contracts


def test_load_contracts_detect_change(small_temp_project, ape_caplog):
    path = small_temp_project.contracts_folder / "Other.json"
    content = path.read_text(encoding="utf8")
    assert "foo" in content, "Unexpected content"

    # Must be compiled first.
    with ape_caplog.at_level(LogLevel.INFO):
        contracts = small_temp_project.load_contracts(use_cache=False)
        assert "Other" in contracts
        ape_caplog.assert_last_log("Compiling")

        ape_caplog.clear()

        # No logs as it doesn't need to re-compile.
        small_temp_project.load_contracts()
        assert not ape_caplog.head

        # Make a change to the file.
        new_content = content.replace("foo", "bar")
        assert "bar" in new_content, "Test setup failed. Unexpected file content."
        path.unlink()
        path.write_text(new_content, encoding="utf8")

        # Prove re-compiles.
        contracts = small_temp_project.load_contracts()
        assert "Other" in contracts
        ape_caplog.assert_last_log("Compiling")


def test_load_contracts_after_deleting_same_named_contract(empty_project, compilers, mock_compiler):
    """
    Tests against a scenario where you:

    1. Add and compile a contract
    2. Delete that contract
    3. Add a new contract with same name somewhere else

    Test such that we are able to compile successfully and not get a misleading
    collision error from deleted files.
    """
    init_contract = empty_project.contracts_folder / "foo.__mock__"
    init_contract.parent.mkdir(parents=True, exist_ok=True)
    init_contract.write_text("LALA", encoding="utf8")
    compilers.registered_compilers[".__mock__"] = mock_compiler
    result = empty_project.load_contracts()
    assert "foo" in result

    # Goodbye.
    init_contract.unlink()

    # Since we are changing files mid-session, we need to refresh the project.
    # Typically, users don't have to do this.
    empty_project.refresh_sources()

    result = empty_project.load_contracts()
    assert "foo" not in result  # Was deleted.
    # Also ensure it is gone from paths.
    assert "foo.__mock__" not in [x.name for x in empty_project.sources.paths]

    # Create a new contract with the same name.
    new_contract = empty_project.contracts_folder / "bar.__mock__"
    new_contract.write_text("BAZ", encoding="utf8")
    empty_project.refresh_sources()

    mock_compiler.overrides = {"contractName": "foo"}
    result = empty_project.load_contracts()
    assert "foo" in result


def test_load_contracts_output_abi(smaller_project):
    cfg = {"output_extra": ["ABI"]}
    with smaller_project.temp_config(compile=cfg):
        _ = smaller_project.load_contracts(use_cache=False)
        abi_folder = smaller_project.manifest_path.parent / "abi"
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


def test_load_contracts_use_cache(mocker, smaller_project):
    """
    Showing the 'use_cache=bool' kwarg works.
    """
    compile_spy = mocker.spy(smaller_project.contracts, "_compile")

    smaller_project.manifest.contract_types = {}  # Force initial compile.
    contracts = smaller_project.load_contracts(use_cache=True)
    assert "Other" in contracts  # Other.json contract.
    assert compile_spy.call_args_list[-1][-1]["use_cache"] is True

    # Show they get added to the manifest.
    assert "Other" in smaller_project.manifest.contract_types

    # Show we can use the cache again (no compiling!)
    contracts = smaller_project.load_contracts(use_cache=True)
    assert "Other" in contracts  # Other.json contract.
    assert compile_spy.call_args_list[-1][-1]["use_cache"] is True

    # Show force-recompiles.
    contracts = smaller_project.load_contracts(use_cache=False)
    assert "Other" in contracts  # Other.json contract.
    assert compile_spy.call_args_list[-1][-1]["use_cache"] is False


def test_manifest_path(smaller_project):
    assert smaller_project.manifest_path == smaller_project.path / ".build" / "__local__.json"


def test_clean(small_temp_project):
    small_temp_project.load_contracts()
    assert small_temp_project.manifest_path.is_file()

    small_temp_project.clean()
    assert not small_temp_project.manifest_path.is_file()
    assert small_temp_project._manifest.contract_types is None
    assert small_temp_project.sources._path_cache is None
    assert small_temp_project._manifest.compilers is None


def test_unpack(small_temp_project):
    # Create a none-contract file.
    non_contract_name = "ThisIsNotAContract.txt"
    path = small_temp_project.contracts_folder / non_contract_name
    path.write_text("not a contract", encoding="utf8")

    with create_tempdir() as path:
        small_temp_project.unpack(path)
        assert (path / "contracts" / "Other.json").is_file()

        # Show that even non-contracts end up in the unpacked destination.
        assert (path / "contracts" / non_contract_name).is_file()


def test_unpack_includes_build_file(small_temp_project):
    buildfile = small_temp_project.path / ".build" / "__local__.json"
    buildfile.parent.mkdir(parents=True, exist_ok=True)
    buildfile.write_text("{}", encoding="utf8")

    with create_tempdir() as path:
        small_temp_project.unpack(path)
        assert (path / ".build" / "__local__.json").is_file()


def test_unpack_includes_interfaces():
    iname = "unp_interface"
    with create_tempdir() as path:
        interfaces = path / "interfaces"
        interfaces.mkdir(parents=True, exist_ok=True)
        interface = interfaces / f"{iname}.json"
        interface.write_text("{}", encoding="utf8")

        project = Project(path)
        with create_tempdir() as new_path:
            project.unpack(new_path)
            expected_interface = new_path / "interfaces" / f"{iname}.json"
            assert expected_interface.is_file()


def test_unpack_includes_interfaces_when_part_of_contracts():
    iname = "unp_interface"
    with create_tempdir() as path:
        interfaces = path / "contracts" / "interfaces"
        interfaces.mkdir(parents=True, exist_ok=True)
        interface = interfaces / f"{iname}.json"
        interface.write_text("{}", encoding="utf8")

        project = Project(path)
        with create_tempdir() as new_path:
            project.unpack(new_path)
            expected_interface = new_path / "contracts" / "interfaces" / f"{iname}.json"
            assert expected_interface.is_file()


def test_add_compiler_data(project_with_dependency_config):
    project_with_dependency_config.clean()

    # NOTE: Using different project than default to lessen
    #   chance of race-conditions from multiprocess test runners.
    project = project_with_dependency_config

    # Load contracts so that any compilers that may exist are present.
    project.load_contracts()

    compiler = Compiler(
        name="comp",
        version="1.0.0",
        contractTypes=["foo"],
        settings={"outputSelection": {"path/to/Foo.sol": "*"}},
    )

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
    project.add_compiler_data([compiler])
    project.add_compiler_data([compiler])

    if compiler.name not in [x.name for x in project.manifest.compilers]:
        names = [x.name for x in project.manifest.compilers]
        pytest.fail(f"Missing expected compiler with name '{compiler.name}'. Names: {names}")
    if compiler.version not in [x.version for x in project.manifest.compilers]:
        pytest.fail(f"Missing expected compiler with version '{compiler.version}'")

    # NOTE: `add_compiler_data()` will not override existing compilers.
    #   Use `update_cache()` for that.
    compiler_2 = Compiler(
        name="test",
        version="2.0.0",
        contractTypes=["bar", "stay"],
        settings={"outputSelection": {"path/to/Bar.vy": "*", "stay.vy": "*"}},
    )
    project.add_compiler_data([compiler_2])
    assert project.manifest.compilers == [compiler, compiler_2]

    # NOTE: Has same contract as compiler 2 and thus replaces the contract.
    compiler_3 = Compiler(
        name="test",
        version="3.0.0",
        contractTypes=["bar"],
        settings={"outputSelection": {"path/to/Bar.vy": "*"}},
    )
    project.add_compiler_data([compiler_3])
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
    project.add_compiler_data([compiler_3])
    comp_check = [
        c for c in project.manifest.compilers if c.name == "test" and c.version == "2.0.0"
    ]
    assert not comp_check

    # Show error on multiple of same compiler.
    compiler_4 = Compiler(name="test123", version="3.0.0", contractTypes=["bar"])
    compiler_5 = compiler_4.model_copy(update={"contractTypes": ["baz"]})
    with pytest.raises(ProjectError, match=r".*was given multiple of the same compiler.*"):
        project.add_compiler_data([compiler_4, compiler_5])

    # Show error when contract type collision (only happens with inputs, else latter replaces).
    compiler_5.contractTypes = ["bar"]
    compiler_5.name = f"{compiler_5.name}new"
    with pytest.raises(ProjectError, match=r".*'bar' collision across compilers.*"):
        project.add_compiler_data([compiler_4, compiler_5])


def test_project_api_foundry_and_ape_config_found(foundry_toml):
    """
    If a project is both a Foundry project and an Ape project,
    ensure both configs are honored.
    """
    with create_tempdir() as tmpdir:
        foundry_cfg_file = tmpdir / "foundry.toml"
        foundry_cfg_file.write_text(foundry_toml, encoding="utf8")

        ape_cfg_file = tmpdir / "ape-config.yaml"
        ape_cfg_file.write_text("name: testfootestfootestfoo", encoding="utf8")

        temp_project = Project(tmpdir)
        assert isinstance(temp_project.project_api, MultiProject)

        # This came from the ape config file.
        assert temp_project.config.name == "testfootestfootestfoo"

        # This came from the foundry toml file.
        assert temp_project.config.contracts_folder == "src"
        assert len(temp_project.config.solidity.import_remapping) > 0


def test_get_contract(smaller_project):
    actual = smaller_project.get_contract("Other")
    assert isinstance(actual, ContractContainer), f"{type(actual)}"
    assert actual.contract_type.name == "Other"

    # Ensure manifest is only loaded once by none-ing out the path.
    # Otherwise, this can be a MAJOR performance hit.
    manifest_path = smaller_project.manifest_path
    smaller_project.manifest_path = None
    try:
        actual = smaller_project.get_contract("Other")
        assert isinstance(actual, ContractContainer)
        assert actual.contract_type.name == "Other"
    finally:
        smaller_project.manifest_path = manifest_path


def test_get_contract_not_exists(smaller_project):
    actual = smaller_project.get_contract("this is not a contract")
    assert actual is None


class TestProject:
    """
    All tests related to ``ape.Project``.
    """

    def test_init(self, with_dependencies_project_path):
        # Purpose not using `project_with_contracts` fixture.
        project = Project(with_dependencies_project_path)

        # NOTE: Using tempdir to avoid clashing with other tests during x-dist.
        with project.isolate_in_tempdir() as temp_project:
            assert project.path == with_dependencies_project_path
            project.manifest_path.unlink(missing_ok=True)

            #  Re-init to show it doesn't create the manifest file.
            _ = Project(temp_project.path)

    def test_init_invalid_config(self):
        here = os.curdir
        with create_tempdir() as temp_dir:
            cfgfile = temp_dir / "ape-config.yaml"
            # Name is invalid!
            cfgfile.write_text("name:\n  {asdf}")

            os.chdir(temp_dir)
            expected = r"[.\n]*Input should be a valid string\n-->1: name:\n   2:   {asdf}[.\n]*"
            weird_project = Project(temp_dir)
            try:
                with pytest.raises(ConfigError, match=expected):
                    _ = weird_project.path
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
        Show if contract-types are missing but contracts set,
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
""".lstrip().replace("    ", "\t")

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
            assert actual_sol["via_ir"] is True

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
    def test_lookup(self, smaller_project):
        source_id = smaller_project.Other.contract_type.source_id
        path = smaller_project.sources.lookup(source_id)
        assert path == smaller_project.path / source_id

    def test_lookup_same_source_id_as_local_project(self, smaller_project):
        """
        Tests against a bug where if the source ID of the project matched
        a file in the local project, it would mistakenly return the path
        to the local file instead of the project's file.
        """
        source_id = smaller_project.contracts["Other"].source_id
        path = smaller_project.sources.lookup(source_id)
        assert path.is_file(), "Test path does not exist."

        cfg = {"contracts_folder": smaller_project.config.contracts_folder}
        with Project.create_temporary_project(config_override=cfg) as tmp_project:
            new_source = tmp_project.path / source_id
            new_source.parent.mkdir(parents=True, exist_ok=True)
            new_source.write_text(path.read_text(encoding="utf8"), encoding="utf8")

            actual = tmp_project.sources.lookup(source_id)
            assert actual is not None
            expected = tmp_project.path / source_id
            assert actual == expected

    def test_lookup_missing_extension(self, smaller_project):
        source_id = smaller_project.Other.contract_type.source_id
        source_id_wo_ext = ".".join(source_id.split(".")[:-1])
        path = smaller_project.sources.lookup(source_id_wo_ext)
        assert path == smaller_project.path / source_id

    def test_lookup_mismatched_extension(self, smaller_project):
        source_id = smaller_project.Other.contract_type.source_id
        source_id = source_id.replace(Path(source_id).suffix, ".js")
        path = smaller_project.sources.lookup(source_id)
        assert path is None

    def test_lookup_closest_match(self, smaller_project):
        source_path = smaller_project.contracts_folder / "Other.json"
        temp_dir_a = smaller_project.contracts_folder / "temp"
        temp_dir_b = temp_dir_a / "tempb"
        nested_source_a = temp_dir_a / "Other.json"
        nested_source_b = temp_dir_b / "Other.json"

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
            for base in (source_path, str(source_path), "Other", "Other.json"):
                # Using stem in case it returns `Contract.__mock__`, which is
                # added / removed as part of other tests (running x-dist).
                assert smaller_project.sources.lookup(base).stem == source_path.stem, (
                    f"Failed to lookup {base}"
                )

            # Nested: 1st level
            for closest in (
                nested_source_a,
                str(nested_source_a),
                "temp/Other",
                "temp/Other.json",
            ):
                actual = smaller_project.sources.lookup(closest)
                assert actual

                expected = nested_source_a
                # Using stem in case it returns `Contract.__mock__`, which is
                # added / removed as part of other tests (running x-dist).
                assert actual.stem == expected.stem, f"Failed to lookup {closest}"

            # Nested: 2nd level
            for closest in (
                nested_source_b,
                str(nested_source_b),
                "temp/tempb/Other",
                "temp/tempb/Other.json",
            ):
                actual = smaller_project.sources.lookup(closest)
                expected = nested_source_b

                # Using stem in case it returns `Contract.__mock__`, which is
                # added / removed as part of other tests (running x-dist).
                assert actual.stem == expected.stem, f"Failed to lookup {closest}"

        finally:
            clean()

    def test_lookup_not_found(self, smaller_project):
        assert smaller_project.sources.lookup("madeup.json") is None

    def test_lookup_missing_contracts_prefix(self, smaller_project):
        """
        Show we can exclude the `contracts/` prefix in a source ID.
        """
        actual_from_str = smaller_project.sources.lookup("Other.json")
        actual_from_path = smaller_project.sources.lookup(Path("Other.json"))
        expected = smaller_project.contracts_folder / "Other.json"
        assert actual_from_str == actual_from_path == expected
        assert actual_from_str.is_absolute()
        assert actual_from_path.is_absolute()

    def test_paths_exclude(self, smaller_project):
        exclude_config = {"compile": {"exclude": ["Other.json"]}}
        with smaller_project.temp_config(**exclude_config):
            # Show default excludes also work, such as a .DS_Store file.
            ds_store = smaller_project.contracts_folder / ".DS_Store"
            ds_store.write_bytes(b"asdfasf")

            # Show anything in compiler-cache is ignored.
            cache = smaller_project.contracts_folder / ".cache"
            cache.mkdir(exist_ok=True)
            random_file = cache / "dontmindme.json"
            random_file.write_text("what, this isn't json?!", encoding="utf8")

            path_ids = {
                f"{smaller_project.contracts_folder.name}/{src.name}"
                for src in smaller_project.sources.paths
            }
            excluded = {".DS_Store", "Other.json", ".cache/dontmindme.json"}
            for actual in (path_ids, smaller_project.sources):
                for exclusion in excluded:
                    expected = f"{smaller_project.contracts_folder.name}/{exclusion}"
                    assert expected not in actual

    def test_is_excluded(self, smaller_project):
        exclude_cfg = {"compile": {"exclude": ["exclude_dir/*", "Excl*.json"]}}
        source_ids = ("contracts/exclude_dir/UnwantedContract.json", "contracts/Exclude.json")
        with smaller_project.temp_config(**exclude_cfg):
            for source_id in source_ids:
                path = smaller_project.path / source_id
                assert smaller_project.sources.is_excluded(path)

    def test_items(self, smaller_project):
        actual = list(smaller_project.sources.items())
        assert len(actual) > 0
        assert isinstance(actual[0], tuple)
        assert "contracts/Other.json" in [x[0] for x in actual]
        assert isinstance(actual[0][1], Source)

    def test_keys(self, smaller_project):
        actual = list(smaller_project.sources.keys())
        assert "contracts/Other.json" in actual

    def test_values(self, smaller_project):
        actual = list(smaller_project.sources.values())
        assert all(isinstance(x, Source) for x in actual)


class TestContractManager:
    def test_iter(self, smaller_project):
        actual = list(iter(smaller_project.contracts))
        assert len(actual) > 0
        assert "Other" in actual

    def test_compile(self, smaller_project):
        path = smaller_project.sources.lookup("Other.json")
        actual = list(smaller_project.contracts._compile(path))
        assert len(actual) == 1
        assert actual[0].contract_type.name == "Other"

        # Show it can happen again.
        actual = list(smaller_project.contracts._compile(path))
        assert len(actual) == 1
        assert actual[0].contract_type.name == "Other"

    def test_values(self, small_temp_project):
        actual = [c.name for c in small_temp_project.contracts.values()]
        assert "Other" in actual
        example = small_temp_project.contracts["Other"]
        count = len(small_temp_project.contracts)

        # Delete a file and try again, as a test.
        file = small_temp_project.path / example.source_id
        assert file.is_file()
        file.unlink()

        new_count = len(small_temp_project.contracts)
        assert new_count == count - 1


class TestDeploymentManager:
    def test_track(self, project, owner):
        instance = project.ContractC.deploy(sender=owner)
        project.deployments.track(instance, allow_dev=True)
        contract_type = instance.contract_type
        found = False
        for deployment in project.deployments:
            if deployment.contract_type == f"{contract_type.source_id}:{contract_type.name}":
                found = True
                break

        assert found

    def test_instance_map(self, project, vyper_contract_instance):
        project.deployments.track(vyper_contract_instance, allow_dev=True)
        assert project.deployments.instance_map != {}

        bip122_chain_id = to_hex(project.provider.get_block(0).hash)
        expected_uri = f"blockchain://{bip122_chain_id[2:]}/block/"
        for key in project.deployments.instance_map.keys():
            if key.startswith(expected_uri):
                return

        assert False, "Failed to find expected URI"


def test_chdir(smaller_project):
    original_path = smaller_project.path
    with create_tempdir() as new_path:
        smaller_project.chdir(new_path)
        assert smaller_project.path == new_path

        # Undo.
        smaller_project.chdir(original_path)
        assert smaller_project.path == original_path

        # Show you can also use it in a context.
        with smaller_project.chdir(new_path):
            assert smaller_project.path == new_path

        # It should have automatically undone.
        assert smaller_project.path == original_path


def test_within_project_path():
    start_cwd = Path.cwd()
    with create_tempdir() as new_path:
        project = Project(new_path)
        assert Path.cwd() != new_path

        with project.within_project_path():
            assert Path.cwd() == project.path

    assert Path.cwd() == start_cwd
