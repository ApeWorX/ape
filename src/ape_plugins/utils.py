import os
from typing import Dict, Set, Tuple

from github import Github

from ape.__modules__ import __modules__
from ape.exceptions import ConfigError
from ape.logging import logger

# Plugins maintained OSS by ApeWorX (and trusted)
FIRST_CLASS_PLUGINS = set(__modules__)

SECOND_CLASS_PLUGINS: Set[str] = set()

# TODO: Should the github client be in core?
# TODO: Handle failures with connecting to github (potentially cached on disk?)
if "GITHUB_ACCESS_TOKEN" in os.environ:
    author = Github(os.environ["GITHUB_ACCESS_TOKEN"]).get_organization("ApeWorX")

    SECOND_CLASS_PLUGINS = {
        repo.name.replace("-", "_") for repo in author.get_repos() if repo.name.startswith("ape-")
    }

else:
    logger.warning("$GITHUB_ACCESS_TOKEN not set, unable to list all plugins")


def is_plugin_installed(plugin: str) -> bool:
    try:
        __import__(plugin)
        return True
    except ImportError:
        return False


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
