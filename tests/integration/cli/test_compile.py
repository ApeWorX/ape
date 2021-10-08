def test_compile(ape_cli, runner, project):
    if not (project.path / "contracts").exists():
        result = runner.invoke(ape_cli, ["compile"])
        assert result.exit_code == 0
        assert "WARNING" in result.output
        assert "No 'contracts/' directory detected" in result.output
        return  # Nothing else to test for this project

    if ".test" in project.extensions_with_missing_compilers:
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

        return  # Nothing else to test for this project

    result = runner.invoke(ape_cli, ["compile"])
    assert result.exit_code == 0
    # First time it compiles, it compiles fully
    for file in project.path.glob("contracts/**/*"):
        assert file.stem in result.output

    result = runner.invoke(ape_cli, ["compile"])
    assert result.exit_code == 0
    # First time it compiles, it caches
    for file in project.path.glob("contracts/**/*"):
        assert file.stem not in result.output

    if not any(c.deploymentBytecode for c in project.contracts.values()):
        return  # Only interfaces

    result = runner.invoke(ape_cli, ["compile", "--size"])
    assert result.exit_code == 0
    # Still caches but displays bytecode size
    for file in project.path.glob("contracts/**/*"):
        assert file.stem in result.output
