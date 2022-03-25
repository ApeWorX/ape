import subprocess
import sys
from typing import Dict, List, Optional

from ape.__modules__ import __modules__
from ape.exceptions import ConfigError
from ape.logging import CliLogger
from ape.plugins import clean_plugin_name
from ape.utils import get_package_version, github_client

# Plugins maintained OSS by ApeWorX (and trusted)
CORE_PLUGINS = {p for p in __modules__ if p != "ape"}


def _pip_freeze_plugins() -> List[str]:
    # NOTE: This uses 'pip' subprocess because often we have installed
    # in the same process and this session's site-packages won't know about it yet.
    output = subprocess.check_output([sys.executable, "-m", "pip", "freeze"])
    lines = [
        p
        for p in output.decode().split("\n")
        if p.startswith("ape-") or (p.startswith("-e") and "ape-" in p)
    ]

    new_lines = []
    for package in lines:
        if "==" in package:
            new_lines.append(package)
        elif "-e" in package:
            new_lines.append(package.split(".git")[0].split("/")[-1])

    return new_lines


class ApePlugin:
    def __init__(self, name: str):
        parts = name.split("==")
        self.name = clean_plugin_name(parts[0])  # 'plugin-name'
        self.requested_version = parts[-1] if len(parts) == 2 else None
        self.package_name = f"ape-{self.name}"  # 'ape-plugin-name'
        self.module_name = f"ape_{self.name.replace('-', '_')}"  # 'ape_plugin_name'
        self.current_version = get_package_version(self.package_name)

    def __str__(self):
        return self.name if not self.requested_version else f"{self.name}=={self.requested_version}"

    @classmethod
    def from_dict(cls, data: Dict) -> "ApePlugin":
        if "name" not in data:
            expected_format = (
                "plugins:\n  - name: <plugin-name>\n    version: <plugin-version>  # optional"
            )
            raise ConfigError(
                f"Config item mis-configured. Expected format:\n\n{expected_format}\n"
            )

        name = data.pop("name")
        if "version" in data:
            version = data.pop("version")
            name = f"{name}=={version}"

        if data:
            keys_str = ", ".join(data.keys())
            raise ConfigError(f"Unknown keys for plugins entry '{name}': '{keys_str}'.")

        return ApePlugin(name)

    @property
    def install_str(self) -> str:
        pip_str = str(self.package_name)
        if self.requested_version:
            pip_str = f"{pip_str}=={self.requested_version}"

        return pip_str

    @property
    def can_install(self) -> bool:
        requesting_different_version = (
            self.requested_version is not None and self.requested_version != self.current_version
        )
        return not self.is_installed or requesting_different_version

    @property
    def is_part_of_core(self) -> bool:
        return self.module_name.strip() in CORE_PLUGINS

    @property
    def is_installed(self) -> bool:
        ape_packages = [r.split("==")[0] for r in _pip_freeze_plugins()]
        return self.package_name in ape_packages

    @property
    def pip_freeze_version(self) -> Optional[str]:
        for package in _pip_freeze_plugins():
            parts = package.split("==")
            if len(parts) != 2:
                continue

            name = parts[0]
            if name == self.package_name:
                version_str = parts[-1]
                return version_str

        return None

    @property
    def is_available(self) -> bool:
        return self.module_name in github_client.available_plugins


class ModifyPluginResultHandler:
    def __init__(self, logger: CliLogger, plugin: ApePlugin):
        self._logger = logger
        self._plugin = plugin

    def handle_install_result(self, result) -> bool:
        if not self._plugin.is_installed:
            self._log_modify_failed("install")
            return False
        elif result != 0:
            self._log_errors_occurred("installing")
            return False
        else:
            plugin_id = f"{self._plugin.name}=={self._plugin.pip_freeze_version}"
            self._logger.success(f"Plugin '{plugin_id}' has been installed.")
            return True

    def handle_upgrade_result(self, result, version_before: str) -> bool:
        if result != 0:
            self._log_errors_occurred("upgrading")
            return False

        pip_freeze_version = self._plugin.pip_freeze_version
        if version_before == pip_freeze_version or not pip_freeze_version:
            if self._plugin.requested_version:
                self._logger.info(
                    f"'{self._plugin.name}' already has version '{self._plugin.requested_version}'."
                )
            else:
                self._logger.info(f"'{self._plugin.name}' already up to date.")

            return True
        else:
            self._logger.success(
                f"Plugin '{self._plugin.name}' has been "
                f"upgraded to version {self._plugin.pip_freeze_version}."
            )
            return True

    def handle_uninstall_result(self, result) -> bool:
        if self._plugin.is_installed:
            self._log_modify_failed("uninstall")
            return False
        elif result != 0:
            self._log_errors_occurred("uninstalling")
            return False
        else:
            self._logger.success(f"Plugin '{self._plugin.name}' has been uninstalled.")
            return True

    def _log_errors_occurred(self, verb: str):
        self._logger.error(f"Errors occurred when {verb} '{self._plugin}'.")

    def _log_modify_failed(self, verb: str):
        self._logger.error(f"Failed to {verb} plugin '{self._plugin}.")
