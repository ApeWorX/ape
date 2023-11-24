import subprocess
import sys
from enum import Enum
from functools import cached_property
from typing import Iterator, List, Optional, Sequence, Set, Tuple

from ape.__modules__ import __modules__
from ape._pydantic_compat import root_validator, validator
from ape.logging import logger
from ape.plugins import clean_plugin_name
from ape.utils import BaseInterfaceModel, get_package_version, github_client
from ape.utils.basemodel import BaseModel

# Plugins maintained OSS by ApeWorX (and trusted)
CORE_PLUGINS = {p for p in __modules__ if p != "ape"}


class PluginType(Enum):
    CORE = "core"
    """
    Plugins that ship with the core product.
    """

    INSTALLED = "installed"
    """
    Plugins that are installed (packages).
    """

    THIRD_PARTY = "third-party"
    """
    Plugins that are installed that are not maintained by a trusted source.
    """

    AVAILABLE = "available"
    """
    Plugins that are available to install from a trusted-source.
    """


class _PipFreeze:
    cache: Optional[Set[str]] = None

    def get_plugins(self, use_cache: bool = True) -> Set[str]:
        if use_cache and self.cache is not None:
            return self.cache

        output = subprocess.check_output([sys.executable, "-m", "pip", "freeze"])
        lines = [
            p
            for p in output.decode().splitlines()
            if p.startswith("ape-") or (p.startswith("-e") and "ape-" in p)
        ]

        new_lines = []
        for package in lines:
            if "-e" in package:
                new_lines.append(package.split(".git")[0].split("/")[-1])
            elif "@" in package:
                new_lines.append(package.split("@")[0].strip())
            elif "==" in package:
                new_lines.append(package.split("==")[0].strip())
            else:
                new_lines.append(package)

        self.cache = {x for x in new_lines}
        return self.cache


_pip_freeze = _PipFreeze()


def _pip_freeze_plugins(use_cache: bool = True):
    # NOTE: In a method for mocking purposes in tests.
    return _pip_freeze.get_plugins(use_cache=use_cache)


class PluginMetadataList(BaseModel):
    """
    Metadata per plugin type, including information for all plugins.
    """

    core: "PluginGroup"
    available: "PluginGroup"
    installed: "PluginGroup"
    third_party: "PluginGroup"

    @classmethod
    def from_package_names(cls, packages: Sequence[str]) -> "PluginMetadataList":
        PluginMetadataList.update_forward_refs()
        core = PluginGroup(plugin_type=PluginType.CORE)
        available = PluginGroup(plugin_type=PluginType.AVAILABLE)
        installed = PluginGroup(plugin_type=PluginType.INSTALLED)
        third_party = PluginGroup(plugin_type=PluginType.THIRD_PARTY)
        for name in {p for p in packages}:
            plugin = PluginMetadata(name=name.strip())
            if plugin.in_core:
                core.plugins.append(plugin)
            elif plugin.is_available and not plugin.is_installed:
                available.plugins.append(plugin)
            elif plugin.is_installed and not plugin.in_core and not plugin.is_available:
                third_party.plugins.append(plugin)
            elif plugin.is_installed:
                installed.plugins.append(plugin)
            else:
                logger.error(f"'{plugin.name}' is not a plugin.")

        return cls(core=core, available=available, installed=installed, third_party=third_party)

    def __str__(self) -> str:
        return self.to_str()

    def to_str(self, include: Optional[Sequence[PluginType]] = None) -> str:
        return str(ApePluginsRepr(self, include=include))

    @property
    def all_plugins(self) -> Iterator["PluginMetadata"]:
        yield from self.core.plugins
        yield from self.available.plugins
        yield from self.installed.plugins
        yield from self.third_party.plugins


def _get_available_plugins():
    # NOTE: Wrapped in a method so can GitHub HTTP can be avoided in tests.
    return github_client.available_plugins


class PluginMetadata(BaseInterfaceModel):
    """
    An encapsulation of a request to install a particular plugin.
    """

    name: str
    """The name of the plugin, such as ``trezor``."""

    version: Optional[str] = None
    """The version requested, if there is one."""

    @root_validator(pre=True)
    def validate_name(cls, values):
        if "name" not in values:
            raise ValueError("'name' required.")

        name = values["name"]
        version = values.get("version")

        if version and version.startswith("git+"):
            if f"ape-{name}" not in version:
                # Just some small validation so you can't put a repo
                # that isn't this plugin here. NOTE: Forks should still work.
                raise ValueError("Plugin mismatch with remote git version.")

            version = version

        elif not version:
            # Only check name for version constraint if not in version.
            # NOTE: This happens when using the CLI to provide version constraints.
            for constraint in ("==", "<=", ">=", "@git+"):
                # Version constraint is part of name field.
                if constraint not in name:
                    continue

                # Constraint found.
                name, version = _split_name_and_version(name)
                break

        return {"name": clean_plugin_name(name), "version": version}

    @cached_property
    def package_name(self) -> str:
        """
        Like 'ape-plugin'; the name of the package on PyPI.
        """

        return f"ape-{self.name}"

    @cached_property
    def module_name(self) -> str:
        """
        Like 'ape_plugin' or the name you use when importing.
        """

        return f"ape_{self.name.replace('-', '_')}"

    @cached_property
    def current_version(self) -> Optional[str]:
        """
        The version currently installed if there is one.
        """

        return get_package_version(self.package_name)

    @property
    def install_str(self) -> str:
        """
        The strings you pass to ``pip`` to make the install request,
        such as ``ape-trezor==0.4.0``.
        """

        if self.version and self.version.startswith("git+"):
            # If the version is a remote, you do `pip install git+http://github...`
            return self.version

        # `pip install ape-plugin`
        # `pip install ape-plugin==version`.
        # `pip install "ape-plugin>=0.6,<0.7"`

        version = self.version
        if version and ("=" not in version and "<" not in version and ">" not in version):
            version = f"=={version}"

        return f"{self.package_name}{version}" if version else self.package_name

    @property
    def can_install(self) -> bool:
        """
        ``True`` if the plugin is available and the requested version differs
        from the installed one.  **NOTE**: Is always ``True`` when the plugin
        is not installed.
        """

        requesting_different_version = (
            self.version is not None and self.version != self.current_version
        )
        return not self.is_installed or requesting_different_version

    @property
    def in_core(self) -> bool:
        """
        ``True`` if the plugin is part of the set of core plugins that
        ship with Ape.
        """

        return self.module_name.strip() in CORE_PLUGINS

    @property
    def is_installed(self) -> bool:
        """
        ``True`` if the plugin is installed in the current Python environment.
        """
        return self.check_installed()

    @property
    def is_third_party(self) -> bool:
        return self.is_installed and not self.is_available

    @property
    def pip_freeze_version(self) -> Optional[str]:
        """
        The version from ``pip freeze`` output.
        This is useful because when updating a plugin, it is not available
        until the next Python session but you can use the property to
        verify the update.
        """

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
        """
        Whether the plugin is maintained by the ApeWorX organization.
        """

        return self.module_name in _get_available_plugins()

    def __str__(self):
        """
        A string like ``trezor==0.4.0``.
        """
        if self.version and self.version.startswith("git+"):
            return self.version

        version_key = f"=={self.version}" if self.version and self.version[0].isnumeric() else ""
        return f"{self.name}{version_key}"

    def check_installed(self, use_cache: bool = True):
        ape_packages = [
            _split_name_and_version(n)[0] for n in _pip_freeze_plugins(use_cache=use_cache)
        ]
        return self.package_name in ape_packages


class ModifyPluginResultHandler:
    def __init__(self, plugin: PluginMetadata):
        self._plugin = plugin

    def handle_install_result(self, result) -> bool:
        if not self._plugin.check_installed(use_cache=False):
            self._log_modify_failed("install")
            return False
        elif result != 0:
            self._log_errors_occurred("installing")
            return False
        else:
            plugin_id = self._plugin.name
            version = self._plugin.pip_freeze_version
            if version:
                # Sometimes, like in editable mode, the version is missing here.
                plugin_id = f"{plugin_id}=={version}"

            logger.success(f"Plugin '{plugin_id}' has been installed.")
            return True

    def handle_upgrade_result(self, result, version_before: str) -> bool:
        if result != 0:
            self._log_errors_occurred("upgrading")
            return False

        pip_freeze_version = self._plugin.pip_freeze_version
        if version_before == pip_freeze_version or not pip_freeze_version:
            if self._plugin.version:
                logger.info(f"'{self._plugin.name}' already has version '{self._plugin.version}'.")
            else:
                logger.info(f"'{self._plugin.name}' already up to date.")

            return True
        else:
            logger.success(
                f"Plugin '{self._plugin.name}' has been "
                f"upgraded to version {self._plugin.pip_freeze_version}."
            )
            return True

    def handle_uninstall_result(self, result) -> bool:
        if self._plugin.check_installed(use_cache=False):
            self._log_modify_failed("uninstall")
            return False
        elif result != 0:
            self._log_errors_occurred("uninstalling")
            return False
        else:
            logger.success(f"Plugin '{self._plugin.name}' has been uninstalled.")
            return True

    def _log_errors_occurred(self, verb: str):
        logger.error(f"Errors occurred when {verb} '{self._plugin}'.")

    def _log_modify_failed(self, verb: str):
        logger.error(f"Failed to {verb} plugin '{self._plugin}.")


def _split_name_and_version(value: str) -> Tuple[str, Optional[str]]:
    if "@" in value:
        parts = [x for x in value.split("@") if x]
        return parts[0], "@".join(parts[1:])

    if not (chars := [c for c in ("=", "<", ">") if c in value]):
        return value, None

    index = min(value.index(c) for c in chars)
    return value[:index], value[index:]


class PluginGroup(BaseModel):
    """
    A group of plugin metadata by type.
    """

    plugin_type: PluginType
    plugins: List[PluginMetadata] = []

    def __bool__(self) -> bool:
        return len(self.plugins) > 0

    def __repr__(self) -> str:
        try:
            return f"<{self.name} Plugins Group>"
        except Exception:
            # Prevent exceptions happening in repr()
            logger.log_debug_stack_trace()
            return "<PluginGroup>"

    def __str__(self) -> str:
        return self.to_str()

    @validator("plugin_type")
    def validate_plugin_type(cls, value):
        return PluginType(value) if isinstance(value, str) else value

    @property
    def plugin_type_str(self) -> str:
        return getattr(self.plugin_type, "value", str(self.plugin_type))

    @property
    def name(self) -> str:
        return self.plugin_type_str.capitalize()

    @property
    def plugin_names(self) -> List[str]:
        return [x.name for x in self.plugins]

    def to_str(self, max_length: Optional[int] = None, include_version: bool = True) -> str:
        title = f"{self.name} Plugins"
        if len(self.plugins) <= 0:
            return title

        lines = [title]
        max_length = self.max_name_length if max_length is None else max_length
        plugins_sorted = sorted(self.plugins, key=lambda p: p.name)
        for plugin in plugins_sorted:
            line = plugin.name
            if include_version:
                version = plugin.version or get_package_version(plugin.package_name)
                if version:
                    spacing = (max_length - len(line)) + 4
                    line = f"{line}{spacing * ' '}{version}"

            lines.append(f"  {line}")  # Indent.

        return "\n".join(lines)

    @property
    def max_name_length(self) -> int:
        if not self.plugins:
            return 0

        return max(len(x.name) for x in self.plugins)


class ApePluginsRepr:
    """
    A str-builder for all installed Ape plugins.
    """

    def __init__(
        self, metadata: PluginMetadataList, include: Optional[Sequence[PluginType]] = None
    ):
        self.include = include or (PluginType.INSTALLED, PluginType.THIRD_PARTY)
        self.metadata = metadata

    def __repr__(self) -> str:
        try:
            to_display_str = ", ".join([x.value for x in self.include])
            return f"<PluginMap to_display='{to_display_str}'>"
        except Exception:
            # Prevent exceptions happening in repr()
            logger.log_debug_stack_trace()
            return "<ApePluginsRepr>"

    def __str__(self) -> str:
        sections = []

        if PluginType.CORE in self.include and self.metadata.core:
            sections.append(self.metadata.core)
        if PluginType.INSTALLED in self.include and self.metadata.installed:
            sections.append(self.metadata.installed)
        if PluginType.THIRD_PARTY in self.include and self.metadata.third_party:
            sections.append(self.metadata.third_party)
        if PluginType.AVAILABLE in self.include and self.metadata.available:
            sections.append(self.metadata.available)

        if not sections:
            return ""

        # Use a single max length for all the sections.
        max_length = max(x.max_name_length for x in sections)

        version_skips = (PluginType.CORE, PluginType.AVAILABLE)
        formatted_sections = [
            x.to_str(max_length=max_length, include_version=x.plugin_type not in version_skips)
            for x in sections
        ]
        return "\n\n".join(formatted_sections)
