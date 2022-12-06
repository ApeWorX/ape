from pathlib import Path
import shutil
from tests.integration.cli.utils import run_once

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


@run_once
def test_init_success(ape_cli, runner):
    # Successfull creation of project
    # ape init command

    # removes and cleans cwd
    project_folder = Path.cwd()
    #shutil.rmtree(project_folder)

    # creates the ape project
    result = runner.invoke(ape_cli, ["init"], input="\n".join(["init_success", "y"]))

    assert result.exit_code == 0, result.output
    # checks if the directory existence
    for folder_name in ["contracts", "tests", "scripts"]:
        folder = project_folder / folder_name
        assert folder.exists()

    # checks if the files exist
    git_ignore_file = project_folder / ".gitignore"
    assert git_ignore_file.is_file()
    assert ".env" in git_ignore_file.read_text()

    config = project_folder / "ape-config.yaml"
    assert config.is_file()
    breakpoint()
    assert "init_success" in config.read_text()

    # remove ape project
    shutil.rmtree(project_folder)

    # assert that project folder is removed
    assert not project_folder.exists()


def test_fail_all_files_and_folders_exist():
    # failed to create a folder because it exist
    pass


def test_fail_some_folders_and_files_exist():
    # failed to create a folder because it exist
    pass
