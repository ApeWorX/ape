import sys
from collections.abc import Iterable

from ape.utils._github import _GithubClient, github_client

if sys.version_info.minor >= 11:
    # 3.11 or greater
    # NOTE: type-ignore is for when running mypy on python versions < 3.11
    import tomllib  # type: ignore[import-not-found]
else:
    import toml as tomllib  # type: ignore[no-redef]

from pathlib import Path
from typing import Any, Optional

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

    _github_client: _GithubClient = github_client

    @property
    def foundry_config_file(self) -> Path:
        return self.path / "foundry.toml"

    @property
    def gitmodules_file(self) -> Path:
        return self.path / ".gitmodules"

    @property
    def remapping_file(self) -> Path:
        return self.path / "remapping.txt"

    @property
    def is_valid(self) -> bool:
        return self.foundry_config_file.is_file()

    def extract_config(self, **overrides) -> "ApeConfig":
        ape_cfg: dict = {}

        root_data = self._parse_foundry_toml()

        # Handle root project configuration.
        # NOTE: The default contracts folder name is `src` in foundry
        #  instead of `contracts`, hence the default.
        contracts_folder = root_data.get("src")

        if not contracts_folder:
            if (self.foundry_config_file.parent / "src").is_dir():
                contracts_folder = "src"
            elif (self.foundry_config_file.parent / "contracts").is_dir():
                contracts_folder = "contracts"

        if contracts_folder:
            ape_cfg["contracts_folder"] = contracts_folder

        # Foundry uses git-submodules for dependencies.
        if dependencies := self._parse_dependencies_from_gitmodules():
            ape_cfg["dependencies"] = dependencies

        lib_paths = root_data.get("libs", ("lib",))
        if solidity := self._parse_solidity_config(
            root_data, dependencies, lib_paths, contracts_folder=contracts_folder
        ):
            ape_cfg["solidity"] = solidity

        return ApeConfig.model_validate({**ape_cfg, **overrides})

    def _parse_foundry_toml(self) -> dict:
        data = tomllib.loads(self.foundry_config_file.read_text())
        profile = data.get("profile", {})
        return profile.get("default", {})

    def _parse_dependencies_from_gitmodules(self) -> list[dict]:
        if not self.gitmodules_file.is_file():
            return []

        dependencies: list[dict] = []
        module_data = self._parse_gitmodules()
        for module in module_data:
            if not (url := module.get("url")):
                continue
            elif not url.startswith("https://github.com/"):
                # Not from GitHub.
                continue

            github = url.replace("https://github.com/", "").replace(".git", "")
            dependency = {"github": github}
            version_type, version = self._parse_version_from_module(module)
            dependency[version_type] = version
            dependency["name"] = github.split("/")[-1].lower().replace("_", "-")
            dependencies.append(dependency)

        return dependencies

    def _parse_gitmodules(self) -> list[dict[str, str]]:
        submodules: list[dict[str, str]] = []
        submodule: dict[str, str] = {}
        content = Path(self.gitmodules_file).read_text()

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

    def _parse_version_from_module(
        self, module: dict, default_version: str = "main"
    ) -> tuple[str, str]:
        if "release" in module:
            # Use GitHub version API.
            return ("version", module["release"])

        elif "branch" in module:
            # Use clone-by-reference.
            return ("ref", module["branch"])

        elif "url" not in module:
            return ("ref", default_version)

        url = module["url"]
        github = url.replace("https://github.com/", "").replace(".git", "")
        gh_parts = github.split("/")
        if len(gh_parts) != 2:
            # Likely not possible, but just try `main`.
            return ("ref", default_version)

        # Use the default branch of the repo.
        org_name, repo_name = github.split("/")
        repo = self._github_client.get_repo(org_name, repo_name)
        return ("ref", repo.get("default_branch", default_version))

    def _parse_solidity_config(
        self,
        data: dict,
        dependencies: list[dict],
        lib_paths: Iterable[str],
        contracts_folder: Optional[str] = None,
    ) -> dict:
        sol_cfg: dict = {}

        # Different foundry versions use a different key for the solc version.
        if version := (data.get("solc") or data.get("solc_version")):
            sol_cfg["version"] = version

        if evm_version := data.get("evm_version"):
            sol_cfg["evm_version"] = evm_version

        foundry_remappings = [*data.get("remappings", []), *self._parse_remappings_file()]
        if remappings := self._parse_remappings(
            foundry_remappings, dependencies, lib_paths, contracts_folder=contracts_folder
        ):
            sol_cfg["import_remapping"] = remappings

        return sol_cfg

    def _parse_remappings_file(self) -> list[str]:
        if not self.remapping_file.is_file():
            return []

        return self.remapping_file.read_text(encoding="utf8").splitlines()

    def _parse_remappings(
        self,
        foundry_remappings: list[str],
        dependencies: list[dict],
        lib_paths: Iterable[str],
        contracts_folder: Optional[str] = None,
    ) -> list[str]:
        ape_sol_remappings: set[str] = set()

        for f_remap in foundry_remappings:
            key, value = f_remap.split("=")
            sep = "\\" if "\\" in value else "/"
            real_key = key.rstrip(sep)
            clean_key = real_key.lstrip("@")

            # Check if is from one of the dependencies.
            is_dep = False
            repo = value
            for lib_path in lib_paths:
                if not value.startswith(f"{lib_path}{sep}"):
                    continue

                # Dependency found.
                is_dep = True
                repo = value.replace(f"{lib_path}{sep}", "").strip(sep)
                break

            if not is_dep:
                # Append as-is.
                ape_sol_remappings.add(f_remap)
                continue

            # Setup remapping to a dependency in a way Ape expects.
            # Also, change the name of the dependencies to be the short name
            # from the remapping (also what Ape expects).
            dep_found = False
            for dependency in dependencies:
                # NOTE: There appears to be no rhyme or reason to
                # dependency short-names in foundry.
                if (
                    not dependency["github"].endswith(clean_key)
                    and dependency["name"] != clean_key
                    and dependency["name"] != repo
                ):
                    continue

                # Matching dependency found.
                dependency["name"] = clean_key
                version = dependency.get("version") or dependency.get("ref")
                prefix = f"{sep}.cache{sep}"
                if contracts_folder:
                    prefix = f"{contracts_folder}{prefix}"

                value_without_lib_path = value
                for lib_path in lib_paths:
                    if f"{lib_path}{sep}" not in value:
                        continue

                    value_without_lib_path = value.replace(f"{lib_path}{sep}", "")

                # Sometimes, contracts-folder name is included.
                suffix = ""
                if f"{clean_key}{sep}" in value_without_lib_path:
                    suffix = value_without_lib_path.replace(f"{clean_key}{sep}", "").rstrip(sep)

                new_value = f"{prefix}{clean_key}{sep}{version}{sep}{suffix}"
                new_remapping = f"{real_key}={new_value}"
                ape_sol_remappings.add(new_remapping)
                dep_found = True
                break

            if not dep_found:
                # Item seems like a dependency but not found in `dependencies`.
                ape_sol_remappings.add(f_remap)

        return sorted(list(ape_sol_remappings))
