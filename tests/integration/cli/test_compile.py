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
    "script",
    "with-dependencies",
    "with-contracts",
)
def test_compile_missing_contracts_dir(ape_cli, runner, project):
    arg_lists = [("compile",), ("compile", "--include-dependencies")]
    for arg_list in arg_lists:
        result = runner.invoke(ape_cli, arg_list)
        assert result.exit_code == 0, result.output
        assert "WARNING" in result.output, f"Detected contracts folder in '{project.path.name}'"
        assert "Nothing to compile" in result.output


@skip_projects_except("bad-contracts")
def test_compile_skip_contracts_and_missing_compilers(ape_cli, runner, project, switch_config):
    result = runner.invoke(ape_cli, ("compile", "--force"))

    # Default exclude test.
    assert "INFO: Compiling 'subdir/tsconfig.json'." not in result.output
    assert "INFO: Compiling 'package.json'." not in result.output

    # Ensure extensions from exclude (such as .md) don't appear in missing-compilers.
    assert (
        "WARNING: Missing compilers for the following file types: '.foo, .foobar, .test'. "
        "Possibly, a compiler plugin is not installed or is installed but not loading correctly."
    ) in result.output

    # Show we can include custom excludes.
    content = """
    compile:
      exclude:
        - "*Contract2.foo"
    """
    with switch_config(project, content):
        result = runner.invoke(ape_cli, ("compile", "--force"))

        # Show our custom exclude is not mentioned in missing compilers.
        assert "pes: '.foo," not in result.output


@skip_non_compilable_projects
def test_compile(ape_cli, runner, project, clean_cache):
    result = runner.invoke(ape_cli, "compile", catch_exceptions=False)
    assert result.exit_code == 0, result.output

    # First time it compiles, it compiles the files with registered compilers successfully.
    # Files with multiple extensions are currently not supported.
    all_files = [f for f in project.path.glob("contracts/**/*")]

    # Don't expect directories that may happen to have `.json` in name
    # as well as hidden files, such as `.gitkeep`. Both examples are present
    # in the test project!
    excluded = (
        "Exclude.json",
        "UnwantedContract.json",
        "tsconfig.json",
        "package.json",
        "package-lock.json",
    )
    expected_files = [
        f
        for f in all_files
        if f.name.count(".") == 1
        and f.is_file()
        and not f.name.startswith(".")
        and f.name not in excluded
        and f.suffix == ".json"
    ]
    unexpected_files = [f for f in all_files if f not in expected_files]

    manifest = project.extract_manifest()
    non_json = [f for f in expected_files if f.suffix != ".json"]
    if len(non_json) > 0:
        assert manifest.compilers
    for file in expected_files:
        assert file.name in manifest.sources

    missing = [f.name for f in expected_files if f.stem not in result.output]
    assert not missing, f"Missing: {', '.join(missing)}"
    assert not any(f.stem in result.output for f in unexpected_files)

    # Copy in .build to show that those file won't compile.
    # (Anything in a .build is ignored, even if in a contracts folder to prevent accidents).
    shutil.copytree(project.path / ".build", project.contracts_folder / ".build")

    try:
        result = runner.invoke(ape_cli, "compile", catch_exceptions=False)
        assert result.exit_code == 0, result.output
        # First time it compiles, it caches
        for file in project.path.glob("contracts/**/*"):
            assert file.stem not in result.output

    finally:
        shutil.rmtree(project.contracts_folder / ".build", ignore_errors=True)


@skip_projects_except("multiple-interfaces")
def test_compile_when_sources_change(ape_cli, runner, project, clean_cache):
    result = runner.invoke(ape_cli, "compile", catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" in result.output

    # Change the contents of a file
    source_path = project.contracts_folder / "Interface.json"
    modified_source_text = source_path.read_text().replace("foo", "bar")
    source_path.unlink()
    source_path.touch()
    source_path.write_text(modified_source_text)

    result = runner.invoke(ape_cli, "compile", catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" in result.output

    # Verify that the next time, it does not need to recompile (no changes)
    result = runner.invoke(ape_cli, "compile", catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" not in result.output


@skip_projects_except("multiple-interfaces")
def test_compile_when_contract_type_collision(ape_cli, runner, project, clean_cache):
    source_path = project.contracts_folder / "Interface.json"
    temp_dir = project.contracts_folder / "temp"

    def clean():
        if temp_dir.is_dir():
            shutil.rmtree(temp_dir)

    clean()
    source_copy = temp_dir / "Interface.json"
    expected = (
        r"ERROR: \(CompilerError\) ContractType collision between sources '"
        r"([\w\/]+\.json)' and '([\w\/]+\.json)'\."
    )
    temp_dir.mkdir()
    try:
        source_copy.touch()
        source_copy.write_text(source_path.read_text())
        result = runner.invoke(ape_cli, "compile", catch_exceptions=False)
        assert result.exit_code == 1
        actual = result.output
        search_result = re.search(expected, actual)
        assert search_result, actual
        groups = search_result.groups()
        assert {groups[0], groups[1]} == {"Interface.json", "temp/Interface.json"}

    finally:
        clean()


@skip_projects_except("multiple-interfaces")
def test_compile_when_source_contains_return_characters(ape_cli, runner, project, clean_cache):
    """
    This tests a bugfix where a source file contained return-characters
    and that triggered endless re-compiles because it technically contains extra
    bytes than the ones that show up in the text.
    """
    source_path = project.contracts_folder / "Interface.json"
    # Change the contents of a file to contain the '\r' character.
    modified_source_text = f"{source_path.read_text()}\r"
    source_path.unlink()
    source_path.touch()
    source_path.write_text(modified_source_text)

    result = runner.invoke(ape_cli, "compile", catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" in result.output

    # Verify that the next time, it does not need to recompile (no changes)
    result = runner.invoke(ape_cli, "compile", catch_exceptions=False)
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
    result = runner.invoke(ape_cli, ("compile", contract_path), catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" in result.output

    # Already compiled.
    result = runner.invoke(ape_cli, ("compile", contract_path), catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" not in result.output

    # Force recompile.
    result = runner.invoke(ape_cli, ("compile", contract_path, "--force"), catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Compiling 'Interface.json'" in result.output


@skip_projects_except("multiple-interfaces")
def test_compile_unknown_extension_does_not_compile(ape_cli, runner, project, clean_cache):
    name = "Interface.js"
    result = runner.invoke(ape_cli, ("compile", name), catch_exceptions=False)
    expected = f"Source file '{name}' not found."
    assert result.exit_code == 2, result.output
    assert expected in result.output


@skip_projects_except()
def test_compile_contracts(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ("compile", "--size"), catch_exceptions=False)
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
        "manifest-dependency",
    ):
        assert name in list(project.dependencies.keys())
        dependency = project.dependencies[name]["local"]
        assert isinstance(dependency[name], ContractContainer)


@skip_projects_except("with-dependencies")
def test_compile_individual_contract_excludes_other_contract(ape_cli, runner, project):
    result = runner.invoke(ape_cli, ("compile", "Project", "--force"), catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Other" not in result.output


@skip_projects_except("with-dependencies")
def test_compile_non_ape_project_deletes_ape_config_file(ape_cli, runner, project):
    ape_config = project.path / "default" / "ape-config.yaml"
    if ape_config.is_file():
        # Corrupted from a previous test.
        ape_config.unlink()

    result = runner.invoke(ape_cli, ("compile", "Project", "--force"), catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "ape-config.yaml" not in [f.name for f in (project.path / "default").iterdir()]


@skip_projects_except("only-dependencies")
def test_compile_only_dependency(ape_cli, runner, project, clean_cache, caplog):
    expected_log_message = "Compiling 'DependencyInProjectOnly.json'"
    dependency_cache = project.path / "renamed_contracts_folder" / ".build"
    if dependency_cache.is_dir():
        shutil.rmtree(str(dependency_cache))

    result = runner.invoke(ape_cli, ("compile", "--force"), catch_exceptions=False)
    assert result.exit_code == 0, result.output

    # Dependencies are not compiled automatically
    assert expected_log_message not in result.output

    # Trigger actual dependency compilation
    dependency = project.dependencies["dependency-in-project-only"]["local"]
    _ = dependency.DependencyInProjectOnly

    # Pop the log record off here so we can check the tail again below.
    length_before = len(caplog.records)
    assert expected_log_message in caplog.messages[-1]

    # It should not need to compile again.
    _ = dependency.DependencyInProjectOnly
    if caplog.records:
        if expected_log_message in caplog.messages[-1]:
            length_after = len(caplog.records)
            # The only way it should be the same log is if there
            # were not additional logs.
            assert length_after == length_before

        else:
            pytest.fail("Compiled twice!")

    # Force a re-compile and trigger the dependency to compile via CLI
    result = runner.invoke(
        ape_cli, ("compile", "--force", "--include-dependencies"), catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert expected_log_message in result.output

    # Make sure the config option works
    config_file = project.path / "ape-config.yaml"
    text = config_file.read_text()
    try:
        text = text.replace("  include_dependencies: false", "  include_dependencies: true")
        config_file.unlink()
        config_file.write_text(text)
        project.config_manager.load(force_reload=True)
        result = runner.invoke(ape_cli, ("compile", "--force"), catch_exceptions=False)
        assert result.exit_code == 0, result.output
        assert expected_log_message in result.output
    finally:
        text.replace("  include_dependencies: true", "  include_dependencies: false")
        project.config_manager.load(force_reload=True)


@skip_projects_except("with-contracts")
def test_raw_compiler_output_bytecode(ape_cli, runner, project):
    assert project.RawVyperOutput.contract_type.runtime_bytecode.bytecode
    assert project.RawSolidityOutput.contract_type.deployment_bytecode.bytecode


@skip_projects_except("with-contracts")
def test_compile_after_deleting_cache_file(project):
    assert project.RawVyperOutput
    path = project.local_project._cache_folder / "RawVyperOutput.json"
    path.unlink()

    # Should still work (will have to figure it out its missing and put back).
    assert project.RawVyperOutput


@skip_projects_except("with-contracts")
def test_compile_exclude(ape_cli, runner):
    result = runner.invoke(ape_cli, ("compile", "--force"), catch_exceptions=False)
    assert "Compiling 'Exclude.json'" not in result.output
    assert "Compiling 'exclude_dir/UnwantedContract.json'" not in result.output


@skip_projects_except("with-contracts")
def test_compile_config_override(ape_cli, runner):
    arguments = (
        "compile",
        "--force",
        "--config-override",
        '{"compile": {"exclude": ["*ContractA*"]}}',
    )
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert "Compiling 'ContractA.json'" not in result.output
