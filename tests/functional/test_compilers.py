from pathlib import Path

import pytest

from ape.exceptions import APINotImplementedError, CompilerError
from tests.conftest import skip_if_plugin_installed


def test_get_imports(project, compilers):
    # See ape-solidity for better tests
    assert not compilers.get_imports(project.source_paths)


def test_missing_compilers_without_source_files(project):
    result = project.extensions_with_missing_compilers()
    assert result == []


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

    expected = r"Unable to flatten contract\. Missing compiler for '.foo'."
    with pytest.raises(CompilerError, match=expected):
        compilers.flatten_contract(Path("contract.foo"))
