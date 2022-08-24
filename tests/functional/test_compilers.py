def test_get_imports_only_includes_sources_from_compiler(project, compilers):
    # See ape-solidity for better tests
    assert not compilers.get_imports(project.source_paths)
