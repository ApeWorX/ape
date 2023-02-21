import re
import shutil

import pytest

from ape.contracts import ContractContainer

from .utils import skip_projects, skip_projects_except

skip_non_compilable_projects = skip_projects(
    "empty-config",
    "no-config",
    "script",
    "only-dependencies",
    "bad-contracts",
    "test",
    "geth",
)


@skip_projects(
    "geth",
    "multiple-interfaces",
    "only-dependencies",
    "test",
    "bad-contracts",
    "with-dependencies",
    "with-contracts",
)
def test_compile_missing_contracts_dir(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile"])
    assert result.exit_code == 0, result.output
    assert "WARNING" in result.output, f"Detected contracts folder in '{project.path.name}'"
    assert "Nothing to compile" in result.output


@skip_projects_except("bad-contracts")
def test_skip_contracts(ape_cli, runner, project, switch_config):
    result = runner.invoke(ape_cli, ["compile", "--force"])
    assert "INFO: Compiling 'subdir/tsconfig.json'." not in result.output
    assert "INFO: Compiling 'package.json'." not in result.output

    # Simulate configuring Ape to not ignore tsconfig.json for some reason.
    content = """
    compiler:
      ignore_files:
        - "*package.json"
    """
    with switch_config(project, content):
        result = runner.invoke(ape_cli, ["compile", "--force"])
        assert "INFO: Compiling 'subdir/tsconfig.json'." in result.output


@skip_non_compilable_projects
def test_compile(ape_cli, runner, project, clean_cache):
    result = runner.invoke(ape_cli, ["compile"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    # First time it compiles, it compiles the files with registered compilers successfully.
    # Files with multiple extensions are currently not supported.
    all_files = [f for f in project.path.glob("contracts/**/*")]

    # Don't expect directories that may happen to have `.json` in name
    # as well as hidden files, such as `.gitkeep`. Both examples are present
    # in the test project!
    expected_files = [
        f
        for f in all_files
        if f.name.count(".") == 1 and f.is_file() and not f.name.startswith(".")
    ]
    unexpected_files = [f for f in all_files if f not in expected_files]

    manifest = project.extract_manifest()
    for file in expected_files:
        assert file.name in manifest.sources

    assert all([f.stem in result.output for f in expected_files])
    assert not any([f.stem in result.output for f in unexpected_files])

    result = runner.invoke(ape_cli, ["compile"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    # First time it compiles, it caches
    for file in project.path.glob("contracts/**/*"):
        assert file.stem not in result.output


@skip_projects_except("multiple-interfaces")
def test_compile_when_sources_change(ape_cli, runner, project, clean_cache):
    result = runner.invoke(ape_cli, ["compile"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" in result.output

    # Change the contents of a file
    source_path = project.contracts_folder / "Interface.json"
    modified_source_text = source_path.read_text().replace("foo", "bar")
    source_path.unlink()
    source_path.touch()
    source_path.write_text(modified_source_text)

    result = runner.invoke(ape_cli, ["compile"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" in result.output

    # Verify that the next time, it does not need to recompile (no changes)
    result = runner.invoke(ape_cli, ["compile"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" not in result.output


@skip_projects_except("multiple-interfaces")
def test_compile_when_contract_type_collision(ape_cli, runner, project, clean_cache):
    source_path = project.contracts_folder / "Interface.json"
    temp_dir = project.contracts_folder / "temp"
    source_copy = temp_dir / "Interface.json"
    expected = (
        r"ERROR: \(CompilerError\) ContractType collision between sources '"
        r"([\w\/]+\.json)' and '([\w\/]+\.json)'\."
    )
    temp_dir.mkdir()
    try:
        source_copy.touch()
        source_copy.write_text(source_path.read_text())
        result = runner.invoke(ape_cli, ["compile"], catch_exceptions=False)
        assert result.exit_code == 1
        actual = result.output
        search_result = re.search(expected, actual)
        assert search_result, actual
        groups = search_result.groups()
        assert {groups[0], groups[1]} == {"Interface.json", "temp/Interface.json"}

    finally:
        if temp_dir.is_dir():
            shutil.rmtree(temp_dir)


@skip_projects_except("multiple-interfaces")
def test_compile_when_source_contains_return_characters(ape_cli, runner, project, clean_cache):
    # NOTE: This tests a bugfix where a source file contained return-characters
    # and that triggered endless re-compiles because it technically contains extra
    # bytes than the ones that show up in the text.

    # Change the contents of a file to contain the '\r' character.
    source_path = project.contracts_folder / "Interface.json"
    modified_source_text = f"{source_path.read_text()}\r"
    source_path.unlink()
    source_path.touch()
    source_path.write_text(modified_source_text)

    result = runner.invoke(ape_cli, ["compile"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" in result.output

    # Verify that the next time, it does not need to recompile (no changes)
    result = runner.invoke(ape_cli, ["compile"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" not in result.output


@skip_projects_except("multiple-interfaces")
def test_can_access_contracts(project, clean_cache):
    # This test does not use the CLI but still requires a project or run off of.
    assert project.Interface, "Unable to access contract when needing to compile"
    assert project.Interface, "Unable to access contract when not needing to compile"


@skip_projects_except("multiple-interfaces")
@pytest.mark.parametrize(
    "contract_path",
    ("Interface", "Interface.json", "contracts/Interface", "contracts/Interface.json"),
)
def test_compile_specified_contracts(ape_cli, runner, project, contract_path, clean_cache):
    result = runner.invoke(ape_cli, ["compile", contract_path], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" in result.output


@skip_projects_except("multiple-interfaces")
def test_compile_unknown_extension_does_not_compile(ape_cli, runner, project, clean_cache):
    result = runner.invoke(
        ape_cli, ["compile", "Interface.js"], catch_exceptions=False
    )  # Suffix to existing extension
    assert result.exit_code == 2, result.output
    assert "Error: Contract 'Interface.js' not found." in result.output


@skip_projects_except()
def test_compile_contracts(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile", "--size"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    # Still caches but displays bytecode size
    for file in project.path.glob("contracts/**/*"):
        assert file.stem in result.output


@skip_projects_except("with-dependencies")
@pytest.mark.parametrize(
    "contract_path",
    (None, "contracts/", "Project", "contracts/Project.json"),
)
def test_compile_with_dependency(ape_cli, runner, project, contract_path):
    cmd = ["compile", "--force"]

    if contract_path:
        cmd.append(contract_path)

    result = runner.invoke(ape_cli, cmd, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    for name in (
        "default",
        "renamed-contracts-folder",
        "containing-sub-dependencies",
        "renamed-complex-contracts-folder",
        "renamed-contracts-folder-specified-in-config",
    ):
        assert name in list(project.dependencies.keys())
        assert type(project.dependencies[name]["local"]["name"]) == ContractContainer


@skip_projects_except("with-dependencies")
def test_compile_individual_contract_excludes_other_contract(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile", "Project", "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Other" not in result.output


@skip_projects_except("with-dependencies")
def test_compile_non_ape_project_deletes_ape_config_file(ape_cli, runner, project):
    ape_config = project.path / "default" / "ape-config.yaml"
    if ape_config.is_file():
        # Corrupted from a previous test.
        ape_config.unlink()

    result = runner.invoke(ape_cli, ["compile", "Project", "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "ape-config.yaml" not in [f.name for f in (project.path / "default").iterdir()]


@skip_projects_except("only-dependencies")
def test_compile_only_dependency(ape_cli, runner, project, clean_cache, caplog):
    expected_log_message = "Compiling 'DependencyInProjectOnly.json'"
    dependency_cache = project.path / "renamed_contracts_folder" / ".build"
    if dependency_cache.is_dir():
        shutil.rmtree(str(dependency_cache))

    result = runner.invoke(ape_cli, ["compile", "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    # Dependencies are not compiled automatically
    assert expected_log_message not in result.output

    # Trigger actual dependency compilation
    dependency = project.dependencies["dependency-in-project-only"]["local"]
    _ = dependency.DependencyInProjectOnly
    log_record = caplog.records.pop()
    assert expected_log_message in log_record.message

    # It should not need to compile again.
    _ = dependency.DependencyInProjectOnly
    if caplog.records:
        log_record = caplog.records.pop()
        assert expected_log_message not in log_record.message, "Compiled twice!"


@skip_projects_except("with-contracts")
def test_raw_compiler_output_bytecode(ape_cli, runner, project):
    assert project.RawVyperOutput.contract_type.runtime_bytecode.bytecode
    assert project.RawSolidityOutput.contract_type.deployment_bytecode.bytecode


@skip_projects_except("with-contracts")
def test_compile_after_deleting_cache_file(ape_cli, runner, project):
    assert project.RawVyperOutput
    path = project.local_project._cache_folder / "RawVyperOutput.json"
    path.unlink()

    # Should still work (will have to figure it out its missing and put back).
    assert project.RawVyperOutput
