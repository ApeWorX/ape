import pytest

from .utils import skip_projects, skip_projects_except


@skip_projects(["unregistered-contracts", "one-interface", "hello-world"])
def test_compile_missing_contracts_dir(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile"])
    assert result.exit_code == 0
    assert "WARNING" in result.output
    assert "No 'contracts/' directory detected" in result.output


@skip_projects_except(["unregistered-contracts"])
def test_missing_extensions(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile"])
    assert result.exit_code == 0
    assert "WARNING: No compilers detected for the " "following extensions:" in result.output
    assert ".test" in result.output
    assert ".foobar" in result.output

    result = runner.invoke(ape_cli, ["compile", "contracts/Contract.test"])
    assert result.exit_code == 0
    assert (
        "WARNING: No compilers detected for the " "following extensions: .test"
    ) in result.output


@skip_projects(["empty-config", "no-config", "script", "unregistered-contracts"])
def test_compile(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile"])
    assert result.exit_code == 0, result.output
    # First time it compiles, it compiles fully
    for file in project.path.glob("contracts/**/*"):
        assert file.stem in result.output

    result = runner.invoke(ape_cli, ["compile"])
    assert result.exit_code == 0
    # First time it compiles, it caches
    for file in project.path.glob("contracts/**/*"):
        assert file.stem not in result.output


@skip_projects_except(["hello-world"])
@pytest.mark.parametrize(
    "contract_path",
    ("HelloWorld", "HelloWorld.sol", "contracts/HelloWorld", "contracts/HelloWorld.sol"),
)
def test_compile_specified_contracts(ape_cli, runner, project, contract_path, clean_cache):
    result = runner.invoke(ape_cli, ["compile", contract_path])
    assert result.exit_code == 0, result.output
    assert "Compiling 'contracts/HelloWorld.sol'" in result.output


@skip_projects_except([])
def test_compile_contracts(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ["compile", "--size"])
    assert result.exit_code == 0
    # Still caches but displays bytecode size
    for file in project.path.glob("contracts/**/*"):
        assert file.stem in result.output
