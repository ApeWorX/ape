from collections.abc import Iterator

from ape.api.projects import DependencyAPI, ProjectAPI

from .pluggy_patch import PluginType, hookspec


class ProjectPlugin(PluginType):
    """
    A plugin for converting files to a ``PackageManifest``.
    The default project plugin is the :class:`~ape.api.projects.ApeProject`.
    Otherwise, you can define your own project implementation for converting
    a set of files to a ``PackageManifest``, such as one that resolves dependencies
    via ``.gitmodules``.
    """

    @hookspec  # type: ignore[empty-body]
    def projects(self) -> Iterator[type[ProjectAPI]]:
        """
        A hook that returns a :class:`~ape.api.projects.ProjectAPI` subclass type.

        Returns:
            type[:class:`~ape.api.projects.ProjectAPI`]
        """


class DependencyPlugin(PluginType):
    """
    A plugin for downloading packages and creating
    :class:`~ape.plugins.project.ProjectPlugin` implementations.
    """

    @hookspec
    def dependencies(self) -> dict[str, type[DependencyAPI]]:  # type: ignore[empty-body]
        """
        A hook that returns a :class:`~ape.api.projects.DependencyAPI` mapped
        to its ``ape-config.yaml`` file dependencies special key. For example,
        when configuring GitHub dependencies, you set the ``github`` key in
        the ``dependencies:`` block of your ``ape-config.yaml`` file and it
        will automatically use this ``DependencyAPI`` implementation.

        Returns:
            type[:class:`~ape.api.projects.DependencyAPI`]
        """
