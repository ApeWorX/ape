import os

from tests.integration.cli.utils import run_once

"""
The purpose of this unit test is to test the functionality of `ape init`

It should test the creation of directories, config.yaml, and .gitginore:
contracts
test
scripts
ape-config.yaml
.gitignore
"""


@run_once
def test_init_success(ape_cli, runner, integ_project):
    # Successful creation of project
    # ape init command

    # Changes cwd to a temporary directory
    project_folder_path = integ_project.path / "init_success"
    project_folder_path.mkdir()
    start_path = os.curdir
    os.chdir(str(project_folder_path))

    try:
        result = runner.invoke(ape_cli, ("init",), input="\n".join(["init_success"]))

        assert result.exit_code == 0, result.output
        # checks if the directory exist
        for folder_name in ["contracts", "tests", "scripts"]:
            folder = project_folder_path / folder_name
            assert folder.is_dir()

        # checks if the files exist
        git_ignore_file = project_folder_path / ".gitignore"
        assert git_ignore_file.is_file()
        assert ".env" in git_ignore_file.read_text()

        config = project_folder_path / "ape-config.yaml"
        assert config.is_file()
        assert "init_success" in config.read_text()

    finally:
        os.chdir(start_path)


@run_once
def test_fail_all_files_and_folders_exist(ape_cli, runner, integ_project):
    # failed to create all folders because they exist
    # ape init command

    # add project folder and directories
    start_path = os.curdir
    project_folder_path = integ_project.path / "init_fail"
    project_folder_path.mkdir()
    os.chdir(str(project_folder_path))

    try:
        for folder_name in ["contracts", "tests", "scripts"]:
            # Create target Directory
            folder = project_folder_path / folder_name
            if not folder.exists():
                folder.mkdir(exist_ok=False)

        result = runner.invoke(ape_cli, ("init",), input="\n".join(["init_fail"]))
        # checks if the directory existence
        assert result.exit_code == 0, result.output
        assert "contracts' exists" in result.output
        assert "scripts' exists" in result.output
        assert "tests' exists" in result.output

    finally:
        os.chdir(start_path)
