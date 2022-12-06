import pytest
import unittest
from pathlib import Path
"""
The purpose of this unit test is to test the funcationality of `ape init`

It should test the creation of directories, config.yaml, and .gitginore:
contracts
test
scripts
ape-config.yaml
.gitignore
"""

def test_github_clone():
    pass

def test_init_success(ape_cli, runner):
#Successfull creation of project
    # ape init command

    project_folder = Path.cwd()/"test_project_folder"
    result = runner.invoke(
        ape_cli,
        ["init"],
        input="init_success")


    assert result.exit_code == 0, result.output
    for folder_name in ["contracts", "tests", "scripts"]:
            # Create target Directory
            folder = project_folder / folder_name
            assert folder.exists()
    

    git_ignore_file = project_folder/".gitignore"
    assert git_ignore_file.is_file()

    config = project_folder/"ape-config.yaml"
    assert config.is_file() 
    assert 'init_success' in config.read_text()

    result = runner.invoke(["rm","-rf", "test"])

    assert project_folder.exists(exist_ok=False)
    

def test_fail_all_files_and_folders_exist():
#failed to create a folder because it exist
    pass

def test_fail_some_folders_and_files_exist():
#failed to create a folder because it exist
    pass