import pytest

from ape.contracts import ContractContainer

from .utils import skip_projects, skip_projects_except


@skip_projects(["unregistered-contracts", "one-interface", "geth", "with-dependency"])
def test_compile_missing_contracts_dir(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile"])
    assert result.exit_code == 0, result.output
    assert "WARNING" in result.output, result.output
    assert "No source files found in" in result.output


@skip_projects_except(["unregistered-contracts"])
def test_missing_extensions(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile"])
    assert result.exit_code == 0, result.output
    assert "WARNING: No compilers detected for the following extensions:" in result.output
    assert ".test" in result.output
    assert ".foobar" in result.output


@skip_projects_except(["unregistered-contracts"])
def test_no_compiler_for_extension(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile", "contracts/Contract.test"])
    assert result.exit_code == 0, result.output
    assert "WARNING: No compilers detected for the following extensions: .test" in result.output


@skip_projects(["empty-config", "no-config", "script", "unregistered-contracts", "test", "geth"])
def test_compile(ape_cli, runner, project, clean_cache):
    result = runner.invoke(ape_cli, ["compile"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    # First time it compiles, it compiles fully
    for file in project.path.glob("contracts/**/*"):
        assert file.stem in result.output
    result = runner.invoke(ape_cli, ["compile"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    # First time it compiles, it caches
    for file in project.path.glob("contracts/**/*"):
        assert file.stem not in result.output


@skip_projects_except(["one-interface"])
def test_can_access_contracts(project, clean_cache):
    # This test does not use the CLI but still requires a project or run off of.
    assert project.Interface, "Unable to access contract when needing to compile"
    assert project.Interface, "Unable to access contract when not needing to compile"


@skip_projects_except(["one-interface"])
@pytest.mark.parametrize(
    "contract_path",
    ("Interface", "Interface.json", "contracts/Interface", "contracts/Interface.json"),
)
def test_compile_specified_contracts(ape_cli, runner, project, contract_path, clean_cache):
    result = runner.invoke(ape_cli, ["compile", contract_path], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" in result.output


@skip_projects_except(["one-interface"])
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


@skip_projects_except(["with-dependency"])
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
    assert "__test_dependency__" in project.dependencies
    assert type(project.dependencies["__test_dependency__"].Dependency) == ContractContainer


@skip_projects_except(["with-dependency"])
def test_compile_individual_contract_excludes_other_contract(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile", "Project", "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Other" not in result.output
