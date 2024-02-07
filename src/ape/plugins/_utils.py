import subprocess
import sys
from enum import Enum
from functools import cached_property
from typing import Any, Dict, Iterator, List, Optional, Sequence, Set, Tuple

import click
from packaging.specifiers import SpecifierSet
from packaging.version import Version
from pkg_resources import working_set
from pydantic import field_validator, model_validator

from ape.__modules__ import __modules__
from ape.logging import logger
from ape.plugins import clean_plugin_name
from ape.utils import BaseInterfaceModel, get_package_version, github_client
from ape.utils.basemodel import BaseModel
from ape.version import version as ape_version_str
from ape_plugins.exceptions import PluginVersionError

# Plugins maintained OSS by ApeWorX (and trusted)
CORE_PLUGINS = {p for p in __modules__ if p != "ape"}


class ApeVersion:
    def __str__(self) -> str:
        return str(self.version)

    def __getitem__(self, item):
        return str(self)[item]

    @cached_property
    def version(self) -> Version:
        return Version(ape_version_str.split("dev")[0].rstrip("."))

    @property
    def major(self) -> int:
        return self.version.major

    @property
    def minor(self) -> int:
        return self.version.minor

    @property
    def is_pre_one(self) -> bool:
        return self.major == 0

    @cached_property
    def version_range(self) -> str:
        return (
            f">=0.{self.minor},<0.{self.minor + 1}"
            if self.major == 0
            else f">={self.major},<{self.major + 1}"
        )

    @property
    def base(self) -> str:
        return f"0.{self.minor}.0" if self.major == 0 else f"{self.major}.0.0"

    @cached_property
    def next_version_range(self) -> str:
        return (
            f">=0.{self.minor + 1},<0.{self.minor + 2}"
            if self.version.major == 0
            else f">={self.major + 1},<{self.major + 2}"
        )

    @cached_property
    def previous_version_range(self) -> str:
        return (
            f">=0.{self.minor - 2},<0.{self.minor - 1}"
            if self.version.major == 0
            else f">={self.major - 2},<{self.major - 1}"
        )

    def would_get_downgraded(self, plugin_version_str: str) -> bool:
        spec_set = SpecifierSet(plugin_version_str)
        for spec in spec_set:
            spec_version = Version(spec.version)
            if spec.operator in ("==", "<", "<=") and (
                (self.is_pre_one and spec_version.major < ape_version.major)
                or (self.is_pre_one and spec_version.minor < ape_version.minor)
            ):
                return True

        return False


ape_version = ApeVersion()


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


def _check_pip_freeze() -> str:
    result = subprocess.check_output([sys.executable, "-m", "pip", "freeze"])
    return result.decode("utf8")


class _PipFreeze:
    cache: Optional[Set[str]] = None

    def get_plugins(self, use_cache: bool = True, use_process: bool = False) -> Set[str]:
        if use_cache and self.cache is not None:
            return self.cache

        lines = [
            p
            for p in (
                _check_pip_freeze().splitlines()
                if use_process
                else [str(x).replace(" ", "==") for x in working_set]
            )
            if p.startswith("ape-") or (p.startswith("-e") and "ape-" in p)
        ]

        # NOTE: Package IDs should look like "name==version"
        #  if version is available.
        package_ids = []
        for package in lines:
            if "-e" in package:
                package_ids.append(package.split(".git")[0].split("/")[-1])
            elif "@" in package:
                package_ids.append(package.split("@")[0].strip())
            elif "==" in package:
                package_ids.append(package)
            else:
                package_ids.append(package)

        self.cache = set(x for x in package_ids)
        return self.cache


_pip_freeze = _PipFreeze()


def _pip_freeze_plugins(use_cache: bool = True, use_process: bool = False):
    # NOTE: In a method for mocking purposes in tests.
    return _pip_freeze.get_plugins(use_cache=use_cache, use_process=use_process)


class PluginMetadataList(BaseModel):
    """
    Metadata per plugin type, including information for all plugins.
    """

    core: "PluginGroup"
    available: "PluginGroup"
    installed: "PluginGroup"
    third_party: "PluginGroup"

    @classmethod
    def load(cls, plugin_manager):
        registered_plugins = plugin_manager.registered_plugins
        available_plugins = github_client.available_plugins
        return cls.from_package_names(registered_plugins.union(available_plugins))

    @classmethod
    def from_package_names(cls, packages: Sequence[str]) -> "PluginMetadataList":
        PluginMetadataList.model_rebuild()
        core = PluginGroup(plugin_type=PluginType.CORE)
        available = PluginGroup(plugin_type=PluginType.AVAILABLE)
        installed = PluginGroup(plugin_type=PluginType.INSTALLED)
        third_party = PluginGroup(plugin_type=PluginType.THIRD_PARTY)
        for name in {p for p in packages}:
            plugin = PluginMetadata(name=name.strip())
            if plugin.in_core:
                core.plugins[name] = plugin
            elif plugin.is_available and not plugin.is_installed:
                available.plugins[name] = plugin
            elif plugin.is_installed and not plugin.in_core and not plugin.is_available:
                third_party.plugins[name] = plugin
            elif plugin.is_installed:
                installed.plugins[name] = plugin
            else:
                logger.error(f"'{plugin.name}' is not a plugin.")

        return cls(core=core, available=available, installed=installed, third_party=third_party)

    def __str__(self) -> str:
        return self.to_str()

    def to_str(self, include: Optional[Sequence[PluginType]] = None) -> str:
        return str(ApePluginsRepr(self, include=include))

    @property
    def all_plugins(self) -> Iterator["PluginMetadata"]:
        yield from self.core.plugins.values()
        yield from self.available.plugins.values()
        yield from self.installed.plugins.values()
        yield from self.third_party.plugins.values()

    def get_plugin(self, name: str) -> Optional["PluginMetadata"]:
        name = name if name.startswith("ape_") else f"ape_{name}"
        if name in self.core.plugins:
            return self.core.plugins[name]
        elif name in self.installed.plugins:
            return self.installed.plugins[name]
        elif name in self.third_party.plugins:
            return self.third_party.plugins[name]
        elif name in self.available.plugins:
            return self.available.plugins[name]

        return None


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

    _use_subprocess_pip_freeze: bool = False
    """
    Set to True if verifying changes.
    """

    @model_validator(mode="before")
    @classmethod
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
        if version:
            if not any(x in version for x in ("=", "<", ">")):
                version = f"=={version}"

            # Validate we are not attempting to install a plugin
            # that would change the core-Ape version.
            if ape_version.would_get_downgraded(version):
                raise PluginVersionError(
                    "install", "Doing so will downgrade Ape's version.", "Downgrade Ape first."
                )

        elif not version:
            # When not specifying the version, use a default one that
            # won't dramatically change Ape's version.
            version = ape_version.version_range

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

        for package in _pip_freeze_plugins(
            use_cache=False, use_process=self._use_subprocess_pip_freeze
        ):
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
            _split_name_and_version(n)[0]
            for n in _pip_freeze_plugins(
                use_cache=use_cache, use_process=self._use_subprocess_pip_freeze
            )
        ]
        return self.package_name in ape_packages

    def _prepare_install(
        self, upgrade: bool = False, skip_confirmation: bool = False
    ) -> Optional[Dict[str, Any]]:
        # NOTE: Internal and only meant to be called by the CLI.
        if self.in_core:
            logger.error(f"Cannot install core 'ape' plugin '{self.name}'.")
            return None

        elif self.version is not None and upgrade:
            logger.error(
                f"Cannot use '--upgrade' option when specifying "
                f"a version for plugin '{self.name}'."
            )
            return None

        # if plugin is installed but not trusted. It must be a third party
        elif self.is_third_party:
            logger.warning(f"Plugin '{self.name}' is not an trusted plugin.")

        result_handler = ModifyPluginResultHandler(self)
        pip_arguments = [sys.executable, "-m", "pip", "install"]

        if upgrade:
            logger.info(f"Upgrading '{self.name}' plugin ...")

            # NOTE: A simple --upgrade flag may upgrade the plugin
            # to a version outside Core Ape's. Thus, we handle it
            # with a version-specifier instead.
            pip_arguments.extend(
                ("--upgrade", f"{self.package_name}{ape_version.version_range}", "--quiet")
            )
            version_before = self.current_version
            return {
                "args": pip_arguments,
                "version_before": version_before,
                "result_handler": result_handler,
            }

        elif self.can_install and (
            self.is_available
            or skip_confirmation
            or click.confirm(f"Install the '{self.name}' plugin?")
        ):
            logger.info(f"Installing '{self}' plugin ...")
            pip_arguments.extend((self.install_str, "--quiet"))
            return {"args": pip_arguments, "result_handler": result_handler}

        else:
            logger.warning(
                f"'{self.name}' is already installed. Did you mean to include '--upgrade'?"
            )
            return None


class ModifyPluginResultHandler:
    def __init__(self, plugin: PluginMetadata):
        self._plugin = plugin

    def handle_install_result(self, result: int) -> bool:
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

    def handle_upgrade_result(self, result: int, version_before: str) -> bool:
        if result != 0:
            self._log_errors_occurred("upgrading")
            return False

        version_now = self._plugin.pip_freeze_version
        if version_now is not None and version_before == version_now:
            logger.info(f"'{self._plugin.name}' already has version '{version_now}'.")
            return True

        elif self._plugin.pip_freeze_version:
            logger.success(
                f"Plugin '{self._plugin.name}' has been "
                f"upgraded to version {self._plugin.pip_freeze_version}."
            )
            return True

        else:
            # The process was successful but there is still no pip freeze version.
            # This may happen when installing things from GitHub.
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
    plugins: Dict[str, PluginMetadata] = {}

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

    @field_validator("plugin_type", mode="before")
    @classmethod
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
        return [x.name for x in self.plugins.values()]

    def to_str(self, max_length: Optional[int] = None, include_version: bool = True) -> str:
        title = f"{self.name} Plugins"
        if len(self.plugins) <= 0:
            return title

        lines = [title]
        max_length = self.max_name_length if max_length is None else max_length
        plugins_sorted = sorted(self.plugins.values(), key=lambda p: p.name)
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

        return max(len(x) for x in self.plugin_names)


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
