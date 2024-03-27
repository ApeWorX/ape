from pathlib import Path

import pytest

from ape.contracts import ContractContainer
from ape.exceptions import APINotImplementedError, CompilerError
from tests.conftest import skip_if_plugin_installed


def test_get_imports(project, compilers):
    # See ape-solidity for better tests
    assert not compilers.get_imports(project.sources.paths)


@skip_if_plugin_installed("vyper", "solidity")
def test_missing_compilers_error_message(project_with_source_files_contract, sender):
    missing_exts = (".sol", ".vy")
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
    _ = compilers.registered_compilers  # Ensures cached property is set.

    # Hack in our mock compiler.
    compilers.__dict__["registered_compilers"][mock_compiler.ext] = mock_compiler

    try:
        compiler_0 = compilers.get_compiler("mock", settings={"bar": "foo"})
        compiler_1 = compiler_0.get_compiler("mock", settings={"foo": "bar"})

    finally:
        if mock_compiler.ext in compilers.__dict__.get("registered_compilers", {}):
            del compilers.__dict__["registered_compilers"][mock_compiler.ext]

    assert compiler_0.compiler_settings != compiler_1.compiler_settings
    assert id(compiler_0) != id(compiler_1)


def test_getattr(compilers):
    compiler = compilers.ethpm
    assert compiler.name == "ethpm"
    expected = (
        r"'CompilerManager' object has no attribute 'foobar'\. "
        r"Also checked extra\(s\) 'compilers'\."
    )

    with pytest.raises(AttributeError, match=expected):
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
    _ = compilers.registered_compilers  # Ensures cached property is set.

    # Hack in our mock compiler.
    compilers.__dict__["registered_compilers"][mock_compiler.ext] = mock_compiler

    try:
        # Make contracts of type .__mock__ with the same names.
        existing_contract = next(iter(project_with_contract.contracts.values()))
        existing_path = project_with_contract.path / existing_contract.source_id
        new_contract = project_with_contract.path / existing_contract.source_id.replace(
            ".json", mock_compiler.ext
        )
        new_contract.write_text("foobar")
        to_compile = [existing_path, new_contract]
        compile = compilers.compile(to_compile, project=project_with_contract)

        with pytest.raises(CompilerError, match="ContractType collision.*"):
            # Must include existing contract in case not yet compiled.
            _ = list(compile)

    finally:
        if mock_compiler.ext in compilers.__dict__.get("registered_compilers", {}):
            del compilers.__dict__["registered_compilers"][mock_compiler.ext]


def test_compile_with_settings(mock_compiler, compilers, project_with_contract):
    new_contract = project_with_contract.path / f"AMockContract{mock_compiler.ext}"
    new_contract.write_text("foobar")
    settings = {"mock": {"foo": "bar"}}

    _ = compilers.registered_compilers  # Ensures cached property is set.

    # Hack in our mock compiler.
    compilers.__dict__["registered_compilers"][mock_compiler.ext] = mock_compiler

    try:
        list(compilers.compile([new_contract], project=project_with_contract, settings=settings))

    finally:
        if mock_compiler.ext in compilers.__dict__.get("registered_compilers", {}):
            del compilers.__dict__["registered_compilers"][mock_compiler.ext]

    actual = mock_compiler.method_calls[0][2]["settings"]["mock"]
    assert actual == settings["mock"]


def test_compile_str_path(compilers, project_with_contract):
    path = next(iter(project_with_contract.sources.paths))
    actual = list(compilers.compile([str(path)], project=project_with_contract))
    contract_name = path.stem
    assert actual[0].name == contract_name


def test_compile_source(compilers):
    code = '[{"name":"foo","type":"fallback", "stateMutability":"nonpayable"}]'
    actual = compilers.compile_source("ethpm", code)
    assert isinstance(actual, ContractContainer)
