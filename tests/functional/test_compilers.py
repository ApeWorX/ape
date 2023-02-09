import pytest


@pytest.fixture
def skip_if_vyper_or_solidity_installed(compilers):
    registered_compilers = compilers.registered_compilers
    skip_msg = "Cannot have {0} plugin installed to run test!"
    if ".vy" in registered_compilers:
        pytest.skip(skip_msg.format("Vyper"))
    elif ".sol":
        pytest.skip(skip_msg.format("Solidity"))

    yield


def test_get_imports(project, compilers):
    # See ape-solidity for better tests
    assert not compilers.get_imports(project.source_paths)


def test_missing_compilers_without_source_files(project):
    result = project.extensions_with_missing_compilers()
    assert result == []


def test_missing_compilers_with_source_files(
    project_with_source_files_contract, skip_if_vyper_or_solidity_installed
):
    result = project_with_source_files_contract.extensions_with_missing_compilers()
    assert ".vy" in result
    assert ".sol" in result


def test_missing_compilers_error_message(
    project_with_source_files_contract, sender, skip_if_vyper_or_solidity_installed
):
    missing_exts = project_with_source_files_contract.extensions_with_missing_compilers()
    expected = (
        "ProjectManager has no attribute or contract named 'ContractA'. "
        "Could it be from one of the missing compilers for extensions: "
        f'{", ".join(sorted(missing_exts))}?'
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
