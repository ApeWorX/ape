def test_get_imports(project, compilers):
    # See ape-solidity for better tests
    assert not compilers.get_imports(project.source_paths)


def test_extensions_with_missing_compilers(project, compilers):
    result = project.extensions_with_missing_compilers()
    assert result == []
