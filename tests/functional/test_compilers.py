def test_get_imports(project, compilers):
    # See ape-solidity for better tests
    assert not compilers.get_imports(project.source_paths)


def test_missing_compilers_without_source_files(project):
    result = project.extensions_with_missing_compilers()
    assert result == []

def test_missing_compilers_with_source_files(project_with_source_files_contract):
    result = project_with_source_files_contract.extensions_with_missing_compilers()
    assert result == ['.sol', '.vy']