from pathlib import Path

import pytest

from ape.contracts import ContractContainer
from ape.exceptions import APINotImplementedError, CompilerError
from tests.conftest import skip_if_plugin_installed


def test_get_imports(project, compilers):
    # See ape-solidity for better tests
    assert not compilers.get_imports(project.source_paths)


def test_missing_compilers_without_source_files(project):
    result = project.extensions_with_missing_compilers()
    assert result == set()


@skip_if_plugin_installed("vyper", "solidity")
def test_missing_compilers_with_source_files(project_with_source_files_contract):
    result = project_with_source_files_contract.extensions_with_missing_compilers()
    assert ".vy" in result
    assert ".sol" in result


@skip_if_plugin_installed("vyper", "solidity")
def test_missing_compilers_error_message(project_with_source_files_contract, sender):
    missing_exts = project_with_source_files_contract.extensions_with_missing_compilers()
    expected = (
        r"ProjectManager has no attribute or contract named 'ContractA'\. "
        r"However, there is a source file named 'ContractA', "
        r"did you mean to reference a contract name from this source file\? "
        r"Else, could it be from one of the missing compilers for extensions: "
        rf'{", ".join(sorted(missing_exts))}\?'
    )
    with pytest.raises(AttributeError, match=expected):
        project_with_source_files_contract.ContractA.deploy(
            sender.address, sender.address, sender=sender
        )


def test_get_compiler(compilers):
    compiler = compilers.get_compiler("ethpm")
    assert compiler.name == "ethpm"
    assert compilers.get_compiler("foobar") is None


def test_get_compiler_with_settings(compilers, mock_compiler, project_with_contract):
    existing_compilers = compilers._registered_compilers_cache[project_with_contract.path]
    all_compilers = {**existing_compilers, mock_compiler.ext: mock_compiler}

    try:
        compilers._registered_compilers_cache[project_with_contract.path] = all_compilers
        compiler_0 = compilers.get_compiler("mock", settings={"bar": "foo"})
        compiler_1 = compiler_0.get_compiler("mock", settings={"foo": "bar"})

    finally:
        compilers._registered_compilers_cache[project_with_contract.path] = existing_compilers

    assert compiler_0.compiler_settings != compiler_1.compiler_settings
    assert id(compiler_0) != id(compiler_1)


def test_getattr(compilers):
    compiler = compilers.ethpm
    assert compiler.name == "ethpm"

    with pytest.raises(AttributeError, match=r"No attribute or compiler named 'foobar'\."):
        _ = compilers.foobar


def test_supports_tracing(compilers):
    assert not compilers.ethpm.supports_source_tracing


def test_flatten_contract(compilers, project_with_contract):
    """
    Positive tests exist in compiler plugins that implement this behavior.b
    """
    source_id = project_with_contract.ApeContract0.contract_type.source_id
    path = project_with_contract.contracts_folder / source_id

    with pytest.raises(APINotImplementedError):
        compilers.flatten_contract(path)

    expected = r"Unable to flatten contract\. Missing compiler for '.foo'\."
    with pytest.raises(CompilerError, match=expected):
        compilers.flatten_contract(Path("contract.foo"))


def test_contract_type_collision(compilers, project_with_contract, mock_compiler):
    existing_compilers = compilers._registered_compilers_cache[project_with_contract.path]
    all_compilers = {**existing_compilers, mock_compiler.ext: mock_compiler}
    contracts_folder = project_with_contract.contracts_folder

    try:
        compilers._registered_compilers_cache[project_with_contract.path] = all_compilers

        # Make contracts of type .__mock__ with the same names.
        existing_contract = next(iter(project_with_contract.contracts.values()))
        existing_path = contracts_folder / existing_contract.source_id
        new_contract = contracts_folder / f"{existing_contract.name}{mock_compiler.ext}"
        new_contract.write_text("foobar")

        with pytest.raises(CompilerError, match="ContractType collision.*"):
            # Must include existing contract in case not yet compiled.
            compilers.compile([existing_path, new_contract])

    finally:
        compilers._registered_compilers_cache[project_with_contract.path] = existing_compilers


def test_compile_with_settings(mock_compiler, compilers, project_with_contract):
    existing_compilers = compilers._registered_compilers_cache[project_with_contract.path]
    all_compilers = {**existing_compilers, mock_compiler.ext: mock_compiler}
    new_contract = project_with_contract.path / f"AMockContract{mock_compiler.ext}"
    new_contract.write_text("foobar")
    settings = {"mock": {"foo": "bar"}}

    try:
        compilers._registered_compilers_cache[project_with_contract.path] = all_compilers
        compilers.compile([new_contract], settings=settings)

    finally:
        compilers._registered_compilers_cache[project_with_contract.path] = existing_compilers

    actual = mock_compiler.method_calls[0][2]["update"]["compiler_settings"]["mock"]
    assert actual == settings["mock"]


def test_compile_str_path(compilers, project_with_contract):
    path = next(iter(project_with_contract.source_paths))
    actual = compilers.compile([str(path)])
    contract_name = path.stem
    assert actual[contract_name].name == contract_name


def test_compile_source(compilers):
    code = '[{"name":"foo","type":"fallback", "stateMutability":"nonpayable"}]'
    actual = compilers.compile_source("ethpm", code)
    assert isinstance(actual, ContractContainer)
