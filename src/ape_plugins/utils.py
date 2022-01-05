import subprocess
import sys
from typing import Dict, Tuple

from ape.__modules__ import __modules__
from ape.exceptions import ConfigError

# Plugins maintained OSS by ApeWorX (and trusted)
CORE_PLUGINS = {p for p in __modules__ if p != "ape"}


def is_plugin_installed(plugin: str) -> bool:
    plugin = plugin.replace("_", "-")
    reqs = subprocess.check_output([sys.executable, "-m", "pip", "freeze"])
    installed_packages = [r.decode().split("==")[0] for r in reqs.split()]
    return plugin in installed_packages


def extract_module_and_package_install_names(item: Dict) -> Tuple[str, str]:
    """
    Extracts the module name and package name from the configured
    plugin. The package name includes `==<version>` if the version is
    specified in the config.
    """
    try:
        name = item["name"]
        module_name = f"ape_{name.replace('-', '_')}"
        package_install_name = f"ape-{name}"
        version = item.get("version")

        if version:
            package_install_name = f"{package_install_name}=={version}"

        return module_name, package_install_name

    except Exception as err:
        raise _get_config_error() from err


def _get_config_error() -> ConfigError:
    expected_format = "plugins:\n  - name: <plugin-name>\n    version: <plugin-version>  # optional"
    return ConfigError(f"Config item mis-configured. Expected format:\n\n{expected_format}\n")
