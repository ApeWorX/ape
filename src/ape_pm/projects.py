from pathlib import Path
from typing import Any

from yaml import safe_load

from ape.api.config import ApeConfig
from ape.api.projects import ProjectAPI
from ape.utils.os import expand_environment_variables


class BrownieProject(ProjectAPI):
    """
    Allows traditional Brownie projects to work with Ape.
    This class implements the necessary methods in order
    to detect config settings in a Brownie project and
    treat it like an Ape project.
    """

    @property
    def brownie_config_file(self) -> Path:
        return self.path / "brownie-config.yaml"

    @property
    def is_valid(self) -> bool:
        return self.brownie_config_file.is_file()

    def extract_config(self, **overrides) -> ApeConfig:
        migrated_config_data: dict[str, Any] = {}
        text = self.brownie_config_file.read_text()
        text = expand_environment_variables(text)

        try:
            brownie_config_data = safe_load(text) or {}
        except Exception:
            brownie_config_data = {}

        contracts_folder = brownie_config_data.get("contracts_folder", "contracts")
        migrated_config_data["contracts_folder"] = contracts_folder

        # Migrate dependencies
        dependencies = []
        for dependency in brownie_config_data.get("dependencies", []):
            dependency_dict = {}
            dep_parts = dependency.split("/")
            gh_name = dep_parts[0]
            dep_name = gh_name.lower()
            if len(dep_parts) > 1:
                dependency_dict["name"] = dep_name
                if "@" in dep_parts[1]:
                    suffix_parts = dep_parts[1].split("@")
                    dependency_dict["github"] = f"{gh_name}/{suffix_parts[0]}"
                    dependency_dict["version"] = suffix_parts[1]
                else:
                    dependency_dict["github"] = dep_parts[1]

            if dependency_dict:
                dependencies.append(dependency_dict)

        if dependencies:
            migrated_config_data["dependencies"] = dependencies

        # Migrate solidity remapping
        import_remapping = []
        solidity_version = None
        if "compiler" in brownie_config_data:
            compiler_config = brownie_config_data["compiler"]
            if "solc" in compiler_config:
                solidity_config = compiler_config["solc"]
                solidity_version = solidity_config.get("version")

                available_dependencies = [d["name"] for d in dependencies]
                brownie_import_remapping = solidity_config.get("remappings", [])

                for remapping in brownie_import_remapping:
                    parts = remapping.split("=")
                    map_key = parts[0]
                    real_path = parts[1]

                    real_path_parts = real_path.split("/")
                    dependency_name = real_path_parts[0].lower()

                    if dependency_name in available_dependencies:
                        suffix = real_path_parts[1]
                        if "@" in suffix:
                            version_id = suffix.split("@")[1]
                            entry = f"{dependency_name}/{version_id}"
                            import_remapping.append(f"{map_key}={entry}")
                        else:
                            import_remapping.append(f"{map_key}={dependency_name}")

        if import_remapping or solidity_version:
            migrated_solidity_config: dict[str, Any] = {}

            if import_remapping:
                migrated_solidity_config["import_remapping"] = import_remapping

            if solidity_version:
                migrated_solidity_config["version"] = solidity_version

            migrated_config_data["solidity"] = migrated_solidity_config

        model = {**migrated_config_data, **overrides}
        return ApeConfig.model_validate(model)
