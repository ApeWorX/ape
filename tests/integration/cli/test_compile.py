import re
import shutil

import pytest

from ape.contracts import ContractContainer
from ape.utils import get_full_extension

from .utils import skip_projects, skip_projects_except

skip_non_compilable_projects = skip_projects(
    "bad-contracts",
    "empty-config",
    "no-config",
    "only-dependencies",
    "only-script-subdirs",
    "script",
    "test",
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
    arg_lists = [["compile"], ["compile", "--include-dependencies"]]
    for arg_list in arg_lists:
        arg_list.extend(("--project", f"{project.path}"))
        result = runner.invoke(ape_cli, arg_list)
        assert result.exit_code == 0, result.output


@skip_non_compilable_projects
def test_compile(ape_cli, runner, integ_project, clean_cache):
    assert not integ_project.manifest.contract_types, "Setup failed - expecting clean start"
    cmd = ("compile", "--project", f"{integ_project.path}")
    result = runner.invoke(ape_cli, cmd, catch_exceptions=False)
    assert result.exit_code == 0, result.output

    # We have to load the manifest again because normally we are not referencing
    # the manifest in the same process as `ape compile`.
    integ_project.load_manifest()

    assert integ_project.manifest.contract_types

    # First time it compiles, it compiles the files with registered compilers successfully.
    # Files with multiple extensions are currently not supported.
    all_files = [f for f in integ_project.path.glob("contracts/**/*") if f.is_file()]

    # Don't expect directories that may happen to have `.json` in name
    # as well as hidden files, such as `.gitkeep`. Both examples are present
    # in the test project!
    excluded = (
        "Exclude.json",
        "IgnoreUsingRegex.json",
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
        and get_full_extension(f) == ".json"
        and ".cache" not in [p.name for p in f.parents]
    ]
    unexpected_files = [f for f in all_files if f not in expected_files]

    # Extract manifest (note: same project is used in 2 instances here).
    manifest = integ_project.extract_manifest()

    non_json = [f for f in expected_files if get_full_extension(f) != ".json"]
    if len(non_json) > 0:
        assert manifest.compilers
    for file in expected_files:
        assert f"{integ_project.contracts_folder.name}/{file.name}" in manifest.sources

    missing = [f.name for f in expected_files if f.stem not in result.output]

    assert not missing, f"Missing: {', '.join(missing)}"

    for file in unexpected_files:
        assert file.stem not in result.output, f"Shouldn't have compiled {file.name}"

    # Copy in .build to show that those file won't compile.
    # (Anything in a .build is ignored, even if in a contracts folder to prevent accidents).
    build_path = integ_project.path / ".build"
    if integ_project.path != integ_project.contracts_folder:
        shutil.copytree(build_path, integ_project.contracts_folder / ".build")

    assert build_path.is_dir()
    try:
        result = runner.invoke(ape_cli, cmd, catch_exceptions=False)
        assert result.exit_code == 0, result.output
        assert "__local__.json" not in result.output
        # First time it compiles, it caches
        for file in integ_project.path.glob("contracts/**/*"):
            if file.is_file():
                assert file.name not in result.output

    finally:
        shutil.rmtree(integ_project.contracts_folder / ".build", ignore_errors=True)


@skip_projects_except("multiple-interfaces")
def test_compile_when_sources_change(ape_cli, runner, integ_project, clean_cache):
    source_path = integ_project.contracts_folder / "Interface.json"
    content = source_path.read_text()
    assert "bar" in content, "Test setup failed - unexpected content"

    result = runner.invoke(
        ape_cli, ("compile", "--project", f"{integ_project.path}"), catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert "contracts/Interface.json" in result.output
    assert "SUCCESS" in result.output
    assert "'local project' compiled." in result.output

    # Change the contents of a file.
    source_path = integ_project.contracts_folder / "Interface.json"
    modified_source_text = source_path.read_text().replace("bar", "foo")
    source_path.unlink()
    source_path.touch()
    source_path.write_text(modified_source_text, encoding="utf8")
    result = runner.invoke(
        ape_cli, ("compile", "--project", f"{integ_project.path}"), catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert "contracts/Interface.json" in result.output
    assert "SUCCESS" in result.output
    assert "'local project' compiled." in result.output

    # Verify that the next time, it does not need to recompile (no changes)
    result = runner.invoke(
        ape_cli, ("compile", "--project", f"{integ_project.path}"), catch_exceptions=False
    )
    assert result.exit_code == 0, result.output
    assert "contracts/Interface.json" not in result.output


@skip_projects_except("multiple-interfaces")
def test_compile_when_sources_change_problematically(ape_cli, runner, integ_project, clean_cache):
    """
    There was a bug when sources changes but had errors, that the old sources continued
    to be used and the errors were swallowed.
    """
    source_path = integ_project.contracts_folder / "Interface.json"
    content = source_path.read_text()
    assert "bar" in content, "Test setup failed - unexpected content"

    result = runner.invoke(
        ape_cli, ("compile", "--project", f"{integ_project.path}"), catch_exceptions=False
    )
    assert result.exit_code == 0, result.output

    # Change the contents of a file in a problematic way.
    source_path = integ_project.contracts_folder / "Interface.json"
    modified_source_text = source_path.read_text().replace("{", "BRACKET")
    source_path.unlink()
    source_path.touch()
    source_path.write_text(modified_source_text, encoding="utf8")
    result = runner.invoke(
        ape_cli, ("compile", "--project", f"{integ_project.path}"), catch_exceptions=False
    )
    assert result.exit_code != 0, result.output


@skip_projects_except("multiple-interfaces")
def test_compile_when_contract_type_collision(ape_cli, runner, integ_project, clean_cache):
    source_path = integ_project.contracts_folder / "Interface.json"
    temp_dir = integ_project.contracts_folder / "temp"

    def clean():
        if temp_dir.is_dir():
            shutil.rmtree(temp_dir)

    clean()
    source_copy = temp_dir / "Interface.json"
    expected = (
        r"ERROR: *\(CompilerError\) ContractType collision\. "
        r"Contracts '(.*\.json)' and '(.*\.json)' share the name 'Interface'\."
    )
    temp_dir.mkdir()
    try:
        source_copy.touch()
        source_copy.write_text(source_path.read_text(), encoding="utf8")
        result = runner.invoke(
            ape_cli, ("compile", "--project", f"{integ_project.path}"), catch_exceptions=False
        )
        assert result.exit_code == 1
        actual = result.output
        search_result = re.search(expected, actual)
        assert search_result, actual
        groups = search_result.groups()
        expected_group = {"contracts/Interface.json", "contracts/temp/Interface.json"}
        assert set(groups) == expected_group

    finally:
        clean()


@skip_projects_except("multiple-interfaces")
def test_compile_when_source_contains_return_characters(
    ape_cli, runner, integ_project, clean_cache
):
    """
    This tests a bugfix where a source file contained return-characters
    and that triggered endless re-compiles because it technically contains extra
    bytes than the ones that show up in the text.
    """
    source_path = integ_project.contracts_folder / "Interface.json"
    # Change the contents of a file to contain the '\r' character.
    modified_source_text = f"{source_path.read_text()}\r"
    source_path.unlink()
    source_path.touch()
    source_path.write_text(modified_source_text, encoding="utf8")
    arguments = ("compile", "--project", f"{integ_project.path}")
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "contracts/Interface.json" in result.output

    # Verify that the next time, it does not need to recompile (no changes)
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "contracts/Interface.json" not in result.output


@skip_projects_except("multiple-interfaces")
def test_can_access_contracts(integ_project, clean_cache):
    # This test does not use the CLI but still requires a project or run off of.
    assert integ_project.Interface, "Unable to access contract when needing to compile"
    assert integ_project.Interface, "Unable to access contract when not needing to compile"


@skip_projects_except("multiple-interfaces")
@pytest.mark.parametrize(
    "contract_path",
    ("Interface", "Interface.json", "contracts/Interface.json", "contracts/Interface"),
)
def test_compile_specified_contracts(clean_cache, ape_cli, runner, integ_project, contract_path):
    assert integ_project.path.is_dir(), "Setup failed - project missing."

    arguments = ("compile", contract_path, "--project", f"{integ_project.path}")
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "contracts/Interface.json" in result.output

    # Already compiled.
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "contracts/Interface.json" not in result.output

    # Force recompile.
    result = runner.invoke(ape_cli, [*arguments, "--force"], catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "contracts/Interface.json" in result.output


@skip_projects_except("multiple-interfaces")
def test_compile_unknown_extension_does_not_compile(ape_cli, runner, integ_project, clean_cache):
    arguments = ("compile", "Interface.js", "--project", f"{integ_project.path}")
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert result.exit_code == 2, result.output
    assert "Error" in result.output
    assert "Source file 'Interface.js' not found." in result.output


@skip_projects_except("with-dependencies")
@pytest.mark.parametrize(
    "contract_path",
    (None, "contracts/", "Project", "contracts/Project.json"),
)
def test_compile_with_dependency(ape_cli, runner, integ_project, contract_path):
    cmd = ["compile", "--force", "--project", f"{integ_project.path}"]

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
        assert name in list(integ_project.dependencies.keys())
        dependency = integ_project.dependencies[name]["local"]
        assert isinstance(dependency[name], ContractContainer)


@skip_projects_except("with-dependencies")
def test_compile_individual_contract_excludes_other_contract(ape_cli, runner, integ_project):
    arguments = ("compile", "Project", "--force", "--project", f"{integ_project.path}")
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert "Other" not in result.output


@skip_projects_except("with-dependencies")
def test_compile_non_ape_project_deletes_ape_config_file(ape_cli, runner, integ_project):
    ape_config = integ_project.path / "default" / "ape-config.yaml"
    if ape_config.is_file():
        # Corrupted from a previous test.
        ape_config.unlink()

    arguments = ("compile", "Project", "--force", "--project", f"{integ_project.path}")
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert result.exit_code == 0, result.output


@skip_projects_except("only-dependencies")
def test_compile_only_dependency(ape_cli, runner, integ_project, clean_cache, ape_caplog):
    expected_log_message = "Compiling sources/DependencyInProjectOnly.json"

    # Compile w/o --include-dependencies flag (nothing happens but it doesn't fail).
    arguments: tuple[str, ...] = ("compile", "--force", "--project", f"{integ_project.path}")
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert expected_log_message not in result.output

    # Now, actually compile (using --include-dependencies)
    arguments = (
        "compile",
        "--force",
        "--project",
        f"{integ_project.path}",
        "--include-dependencies",
    )
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert expected_log_message in result.output

    # It should not need to compile again (no force).
    arguments = ("compile", "--project", f"{integ_project.path}", "--include-dependencies")
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert expected_log_message not in result.output

    # Ensure config reading works. Note: have to edit file here
    # because in-memory config updates only works when on the subprocess,
    # and the CLI has to reload the project.
    config_path = integ_project.path / "ape-config.yaml"
    integ_project.config.compile.include_dependencies = True
    integ_project.config.write_to_disk(config_path, replace=True)

    arguments = (
        "compile",
        "--force",
        "--project",
        f"{integ_project.path}",
        "--include-dependencies",
    )
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert result.exit_code == 0, result.output
    assert expected_log_message in result.output


@skip_projects_except("with-contracts")
def test_raw_compiler_output_bytecode(integ_project):
    assert integ_project.RawVyperOutput.contract_type.runtime_bytecode.bytecode
    assert integ_project.RawSolidityOutput.contract_type.deployment_bytecode.bytecode


@skip_projects_except("with-contracts")
def test_compile_exclude(ape_cli, runner):
    result = runner.invoke(ape_cli, ("compile", "--force"), catch_exceptions=False)
    assert "Compiling 'contracts/Exclude.json'" not in result.output
    assert "Compiling 'contracts/IgnoreUsingRegex.json'" not in result.output
    assert "Compiling 'contracts/exclude_dir/UnwantedContract.json'" not in result.output


@skip_projects_except("with-contracts")
def test_compile_config_override(ape_cli, runner):
    arguments = (
        "compile",
        "--force",
        "--config-override",
        '{"compile": {"exclude": ["*ContractA*"]}}',
    )
    result = runner.invoke(ape_cli, arguments, catch_exceptions=False)
    assert "Compiling 'contracts/ContractA.json'" not in result.output
