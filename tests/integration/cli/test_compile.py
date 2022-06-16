import shutil

import pytest

from ape.contracts import ContractContainer

from .utils import skip_projects, skip_projects_except

skip_non_compilable_projects = skip_projects(
    [
        "empty-config",
        "no-config",
        "script",
        "only-dependencies",
        "unregistered-contracts",
        "test",
        "geth",
    ]
)


@skip_projects(
    [
        "unregistered-contracts",
        "multiple-interfaces",
        "geth",
        "only-dependencies",
        "with-dependencies",
    ]
)
def test_compile_missing_contracts_dir(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile"])
    assert result.exit_code == 0, result.output
    assert "WARNING" in result.output, result.output
    assert "Nothing to compile" in result.output


@skip_projects_except(["unregistered-contracts"])
def test_missing_extensions(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile", "--force"])
    assert result.exit_code == 0, result.output
    assert "WARNING: No compilers detected for the following extensions:" in result.output
    assert ".test" in result.output
    assert ".foobar" in result.output


@skip_projects_except(["unregistered-contracts"])
def test_no_compiler_for_extension(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile", "contracts/Contract.test"])
    assert result.exit_code == 0, result.output
    assert "WARNING: No compilers detected for the following extensions: .test" in result.output


@skip_non_compilable_projects
def test_compile(ape_cli, runner, project, clean_cache):
    result = runner.invoke(ape_cli, ["compile"], catch_exceptions=False)
    assert result.exit_code == 0, result.output

    # First time it compiles, it compiles the files with registered compilers successfully.
    # Files with multiple extensions are currently not supported.
    all_files = [f for f in project.path.glob("contracts/**/*")]
    expected_files = [f for f in all_files if f.name.count(".") == 1]
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


@skip_projects_except(["multiple-interfaces"])
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


@skip_projects_except(["multiple-interfaces"])
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


@skip_projects_except(["multiple-interfaces"])
def test_can_access_contracts(project, clean_cache):
    # This test does not use the CLI but still requires a project or run off of.
    assert project.Interface, "Unable to access contract when needing to compile"
    assert project.Interface, "Unable to access contract when not needing to compile"


@skip_projects_except(["multiple-interfaces"])
@pytest.mark.parametrize(
    "contract_path",
    ("Interface", "Interface.json", "contracts/Interface", "contracts/Interface.json"),
)
def test_compile_specified_contracts(ape_cli, runner, project, contract_path, clean_cache):
    result = runner.invoke(ape_cli, ["compile", contract_path], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" in result.output


@skip_projects_except(["multiple-interfaces"])
def test_compile_unknown_extension_does_not_compile(ape_cli, runner, project, clean_cache):
    result = runner.invoke(
        ape_cli, ["compile", "Interface.js"], catch_exceptions=False
    )  # Suffix to existing extension
    assert result.exit_code == 2, result.output
    assert "Error: Contract 'Interface.js' not found." in result.output


@skip_projects_except([])
def test_compile_contracts(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile", "--size"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    # Still caches but displays bytecode size
    for file in project.path.glob("contracts/**/*"):
        assert file.stem in result.output


@skip_projects_except(["with-dependencies"])
@pytest.mark.parametrize(
    "contract_path",
    (None, "contracts/", "Project", "contracts/Project.json"),
)
def test_compile_with_dependency(ape_cli, runner, project, contract_path):
    cmd = ["compile", "--force"]

    if contract_path:
        cmd.append(contract_path)

    result = runner.invoke(ape_cli, cmd, catch_exceptions=False)
    assert result.exit_code == 0
    for name in (
        "default",
        "renamed_contracts_folder",
        "containing_sub_dependencies",
        "renamed_complex_contracts_folder",
    ):
        assert name in project.dependencies
        assert type(project.dependencies[name]["local"]["name"]) == ContractContainer


@skip_projects_except(["with-dependencies"])
def test_compile_individual_contract_excludes_other_contract(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile", "Project", "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Other" not in result.output


@skip_projects_except(["with-dependencies"])
def test_compile_non_ape_project_deletes_ape_config_file(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile", "Project", "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "ape-config.yaml" not in [f.name for f in (project.path / "default").iterdir()]


@skip_projects_except(["only-dependencies"])
def test_compile_only_dependency(ape_cli, runner, project, clean_cache):
    dependency_cache = project.path / "renamed_contracts_folder" / ".build"
    if dependency_cache.is_dir():
        shutil.rmtree(str(dependency_cache))

    result = runner.invoke(ape_cli, ["compile", "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'DependencyInProjectOnly.json'" in result.output
