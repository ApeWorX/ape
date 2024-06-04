import os
import sys

if sys.version_info.minor >= 11:
    # 3.11 or greater
    # NOTE: type-ignore is for when running mypy on python versions < 3.11
    import tomllib  # type: ignore[import-not-found]
else:
    import toml as tomllib  # type: ignore[no-redef]

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


class FoundryProject(ProjectAPI):
    """
    Helps Ape read configurations from foundry projects
    and lessens the need of specifying ``config_override:``
    for foundry-based dependencies.
    """

    @property
    def foundry_config_file(self) -> Path:
        return self.path / "foundry.toml"

    @property
    def submodules_file(self) -> Path:
        return self.path / ".gitmodules"

    @property
    def is_valid(self) -> bool:
        return self.foundry_config_file.is_file()

    def extract_config(self, **overrides) -> "ApeConfig":
        ape_cfg: dict = {}
        data = tomllib.loads(self.foundry_config_file.read_text())
        profile = data.get("profile", {})
        root_data = profile.get("default", {})

        # Handle root project configuration.
        # NOTE: The default contracts folder name is `src` in foundry
        #  instead of `contracts`, hence the default.
        ape_cfg["contracts_folder"] = root_data.get("src", "src")

        # Used for seeing which remappings are comings from dependencies.
        lib_paths = root_data.get("libs", ("lib",))

        # Handle all ape-solidity configuration.
        solidity_data: dict = {}
        if solc_version := (root_data.get("solc") or root_data.get("solc_version")):
            solidity_data["version"] = solc_version
        if remappings := root_data.get("remappings"):
            solidity_data["import_remappings"] = remappings
        if "optimizer" in root_data:
            solidity_data["optimize"] = root_data["optimizer"]
        if runs := solidity_data.get("optimizer_runs"):
            solidity_data["optimization_runs"] = runs
        if soldata := solidity_data:
            ape_cfg["solidity"] = soldata

        # Foundry used .gitmodules for dependencies.
        dependencies: list[dict] = []
        if self.submodules_file.is_file():
            module_data = _parse_gitmodules(self.submodules_file)
            for module in module_data:
                if not (url := module.get("url")):
                    continue
                elif not url.startswith("https://github.com/"):
                    # Not from GitHub.
                    continue

                path_name = module.get("path")
                github = url.replace("https://github.com/", "")
                gh_dependency = {"github": github}

                # Check for short-name in remappings.
                fixed_remappings: list[str] = []
                for remapping in ape_cfg.get("solidity", {}).get("import_remappings", []):
                    parts = remapping.split("=")
                    value = parts[1]
                    found = False
                    for lib_path in lib_paths:
                        if not value.startswith(path_name):
                            continue

                        new_value = value.replace(f"{lib_path}{os.path.sep}", "")
                        fixed_remappings.append(f"{parts[0]}={new_value}")
                        gh_dependency["name"] = parts[0].strip(" /\\@")
                        found = True
                        break

                    if not found:
                        # Append remapping as-is.
                        fixed_remappings.append(remapping)

                if fixed_remappings:
                    ape_cfg["solidity"]["import_remappings"] = fixed_remappings

                if "name" not in gh_dependency and path_name:
                    found = False
                    for lib_path in lib_paths:
                        if not path_name.startswith(f"{lib_path}{os.path.sep}"):
                            continue

                        name = path_name.replace(f"{lib_path}{os.path.sep}", "")
                        gh_dependency["name"] = name
                        found = True
                        break

                    if not found:
                        name = path_name.replace("/\\_", "-").lower()
                        gh_dependency["name"] = name

                if "release" in module:
                    gh_dependency["version"] = module["release"]
                elif "branch" in module:
                    gh_dependency["ref"] = module["branch"]

                dependencies.append(gh_dependency)

        if deps := dependencies:
            ape_cfg["dependencies"] = deps

        return ApeConfig.model_validate(ape_cfg)


def _parse_gitmodules(file_path: Path) -> list[dict[str, str]]:
    submodules: list[dict[str, str]] = []
    submodule: dict[str, str] = {}
    content = Path(file_path).read_text()

    for line in content.splitlines():
        line = line.strip()
        if line.startswith("[submodule"):
            # Add the submodule we have been building to the list
            # if it exists. This happens on submodule after the first one.
            if submodule:
                submodules.append(submodule)
                submodule = {}

        for key in ("path", "url", "release", "branch"):
            if not line.startswith(f"{key} ="):
                continue

            submodule[key] = line.split("=")[1].strip()
            break  # No need to try the rest.

    # Add the last submodule.
    if submodule:
        submodules.append(submodule)

    return submodules
