import yaml
from ethpm_types.manifest import PackageManifest

from ape.managers.project import BrownieProject


def test_extract_manifest(dependency_config, project_manager):
    # NOTE: Only setting dependency_config to ensure existence of project.
    manifest = project_manager.extract_manifest()
    assert type(manifest) == PackageManifest
    assert type(manifest.compilers) == list


def test_meta(temp_config, project_manager):
    meta_config = {
        "meta": {
            "authors": ["Test Testerson"],
            "license": "MIT",
            "description": "test",
            "keywords": ["testing"],
            "links": {"apeworx.io": "https://apeworx.io"},
        }
    }
    with temp_config(meta_config):
        assert project_manager.meta.authors == ["Test Testerson"]
        assert project_manager.meta.license == "MIT"
        assert project_manager.meta.description == "test"
        assert project_manager.meta.keywords == ["testing"]
        assert "https://apeworx.io" in project_manager.meta.links["apeworx.io"]


def test_brownie_project_configure(config, base_projects_directory):
    project_path = base_projects_directory / "BrownieProject"
    expected_config_file = project_path / "ape-config.yaml"
    if expected_config_file.is_file():
        # Left from previous run
        expected_config_file.unlink()

    project = BrownieProject(path=project_path, contracts_folder="contracts")
    project.configure()
    assert expected_config_file.is_file()

    with open(expected_config_file) as ape_config_file:
        mapped_config_data = yaml.safe_load(ape_config_file)

    # Ensure Solidity and dependencies configuration mapped correctly
    assert mapped_config_data["solidity"]["version"] == "0.6.12"
    assert mapped_config_data["solidity"]["import_remapping"] == [
        "@openzeppelin/contracts=OpenZeppelin/3.1.0"
    ]
    assert mapped_config_data["dependencies"][0]["name"] == "OpenZeppelin"
    assert mapped_config_data["dependencies"][0]["github"] == "OpenZeppelin/openzeppelin-contracts"
    assert mapped_config_data["dependencies"][0]["version"] == "3.1.0"

    expected_config_file.unlink()
