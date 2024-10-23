from pathlib import Path
from re import Pattern
from typing import cast

import pytest
from ethpm_types import ContractType, ErrorABI

from ape.contracts import ContractContainer
from ape.exceptions import APINotImplementedError, CompilerError, ContractLogicError, CustomError
from ape.types.address import AddressType
from ape_compile import Config


def test_get_imports(project, compilers):
    # See ape-solidity for better tests
    assert not compilers.get_imports(project.sources.paths)


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


@pytest.mark.parametrize("factory", (str, Path))
def test_compile(compilers, project_with_contract, factory):
    """
    Testing both stringified paths and path-object paths.
    """
    path = next(iter(project_with_contract.sources.paths))
    actual = compilers.compile((factory(path),))
    contract_name = path.stem
    assert contract_name in [x.name for x in actual]


def test_compile_contract_type_collision(compilers, project_with_contract, mock_compiler):
    _ = compilers.registered_compilers  # Ensures cached property is set.

    # Hack in our mock compiler.
    compilers.__dict__["registered_compilers"][mock_compiler.ext] = mock_compiler

    try:
        # Make contracts of type .__mock__ with the same names.
        existing_contract = next(iter(project_with_contract.contracts.values()))
        assert existing_contract.source_id, "Setup failed: Contract missing source ID!"
        existing_path = project_with_contract.path / existing_contract.source_id
        new_contract = project_with_contract.path / existing_contract.source_id.replace(
            ".json", mock_compiler.ext
        )
        new_contract.write_text("foobar", encoding="utf8")
        to_compile = [existing_path, new_contract]
        compile = compilers.compile(to_compile, project=project_with_contract)

        with pytest.raises(CompilerError, match="ContractType collision.*"):
            # Must include existing contract in case not yet compiled.
            _ = list(compile)

    finally:
        if mock_compiler.ext in compilers.__dict__.get("registered_compilers", {}):
            del compilers.__dict__["registered_compilers"][mock_compiler.ext]


def test_compile_empty(compilers):
    # Also, we are asserting it does no fail.
    assert list(compilers.compile([])) == []


def test_compile_with_settings(mock_compiler, compilers, project_with_contract):
    new_contract = project_with_contract.path / f"AMockContract{mock_compiler.ext}"
    new_contract.write_text("foobar", encoding="utf8")
    settings = {"mock": {"foo": "bar"}}
    _ = compilers.registered_compilers  # Ensures cached property is set.
    # Hack in our mock compiler.
    compilers.__dict__["registered_compilers"][mock_compiler.ext] = mock_compiler

    try:
        list(compilers.compile([new_contract], project=project_with_contract, settings=settings))

    finally:
        if mock_compiler.ext in compilers.__dict__.get("registered_compilers", {}):
            del compilers.__dict__["registered_compilers"][mock_compiler.ext]

    actual = mock_compiler.method_calls[0][2]["settings"]
    assert actual == settings["mock"]


def test_compile_errors(mock_compiler, compilers, project_with_contract):
    new_contract = project_with_contract.path / f"AMockContract{mock_compiler.ext}"
    new_contract.write_text("foobar", encoding="utf8")

    class MyCustomCompilerError(CompilerError):
        pass

    mock_compiler.compile.side_effect = MyCustomCompilerError
    _ = compilers.registered_compilers  # Ensures cached property is set.
    # Hack in our mock compiler.
    compilers.__dict__["registered_compilers"][mock_compiler.ext] = mock_compiler

    try:
        with pytest.raises(MyCustomCompilerError):
            list(compilers.compile([new_contract], project=project_with_contract))

    finally:
        if mock_compiler.ext in compilers.__dict__.get("registered_compilers", {}):
            del compilers.__dict__["registered_compilers"][mock_compiler.ext]


def test_compile_multiple_errors(
    mock_compiler, make_mock_compiler, compilers, project_with_contract
):
    """
    Simulating getting errors from multiple compilers.
    We should get all the errors.
    """
    second_mock_compiler = make_mock_compiler("mock2")
    new_contract_0 = project_with_contract.path / f"AMockContract{mock_compiler.ext}"
    new_contract_0.write_text("foobar", encoding="utf8")
    new_contract_1 = project_with_contract.path / f"AMockContract{second_mock_compiler.ext}"
    new_contract_1.write_text("foobar2", encoding="utf8")

    expected_0 = "this is expected message 0"
    expected_1 = "this is expected message 1"

    class MyCustomCompilerError0(CompilerError):
        def __init__(self):
            super().__init__(expected_0)

    class MyCustomCompilerError1(CompilerError):
        def __init__(self):
            super().__init__(expected_1)

    mock_compiler.compile.side_effect = MyCustomCompilerError0
    second_mock_compiler.compile.side_effect = MyCustomCompilerError1
    _ = compilers.registered_compilers  # Ensures cached property is set.
    # Hack in our mock compilers.
    compilers.__dict__["registered_compilers"][mock_compiler.ext] = mock_compiler
    compilers.__dict__["registered_compilers"][second_mock_compiler.ext] = second_mock_compiler

    try:
        match = rf"{expected_0}\n\n{expected_1}"
        with pytest.raises(CompilerError, match=match):
            list(compilers.compile([new_contract_0, new_contract_1], project=project_with_contract))

    finally:
        for ext in (mock_compiler.ext, second_mock_compiler.ext):
            if ext in compilers.__dict__.get("registered_compilers", {}):
                del compilers.__dict__["registered_compilers"][ext]


def test_compile_source(compilers):
    code = '[{"name":"foo","type":"fallback", "stateMutability":"nonpayable"}]'
    actual = compilers.compile_source("ethpm", code)
    assert isinstance(actual, ContractContainer)


def test_enrich_error_custom_error(chain, compilers):
    abi = [ErrorABI(type="error", name="InsufficientETH", inputs=[])]
    contract_type = ContractType(abi=abi)
    addr = cast(AddressType, "0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD")
    err = ContractLogicError("0x6a12f104", contract_address=addr)

    # Hack in contract-type.
    chain.contracts._local_contract_types[addr] = contract_type

    # Enriching the error should produce a custom error from the ABI.
    actual = compilers.enrich_error(err)

    assert isinstance(actual, CustomError)
    assert actual.__class__.__name__ == "InsufficientETH"


def test_enrich_error_custom_error_with_inputs(compilers, setup_custom_error):
    deadline = 5
    address = "0x3fC91A3afd70395Cd496C647d5a6CC9D4B2b7FAD"
    err = ContractLogicError(
        f"0xd81b2f2e000000000000000000000000000000000000000000000000000000000000000{deadline}",
        contract_address=cast(AddressType, address),
    )
    setup_custom_error(address)

    # Enriching the error should produce a custom error from the ABI.
    actual = compilers.enrich_error(err)

    assert isinstance(actual, CustomError)
    assert actual.__class__.__name__ == "AllowanceExpired"
    assert actual.inputs["deadline"] == deadline
    assert repr(actual) == f"AllowanceExpired(deadline={deadline})"


def test_config_exclude_regex_serialize():
    """
    Show we can to-and-fro with exclude regexes.
    """
    raw_value = 'r"FooBar"'
    cfg = Config(exclude=[raw_value])
    excl = [x for x in cfg.exclude if isinstance(x, Pattern)]
    assert len(excl) == 1
    assert excl[0].pattern == "FooBar"
    # NOTE: Use json mode to ensure we can go from most minimum value back.
    model_dump = cfg.model_dump(mode="json", by_alias=True)
    assert raw_value in model_dump.get("exclude", [])
    new_cfg = Config.model_validate(cfg.model_dump(mode="json", by_alias=True))
    excl = [x for x in new_cfg.exclude if isinstance(x, Pattern)]
    assert len(excl) == 1
    assert excl[0].pattern == "FooBar"
