from typing import Dict, Iterator, Type

from ape.api import DependencyAPI, ProjectAPI

from .pluggy_patch import PluginType, hookspec


class ProjectPlugin(PluginType):
    """
    A plugin for converting files to a ``PackageManifest``.
    The default project plugin is the :class:`~ape.api.projects.ApeProject`.
    Otherwise, you can define your own project implementation for converting
    a set of files to a ``PackageManifest``, such as one that resolves dependencies
    via ``.gitmodules``.
    """

    @hookspec
    def projects(self) -> Iterator[Type[ProjectAPI]]:
        """
        A hook that returns a :class:`~ape.api.projects.ProjectAPI` subclass type.

        Returns:
            Type[:class:`~ape.api.projects.ProjectAPI`]
        """


class DependencyPlugin(PluginType):
    """
    A plugin for downloading packages and creating
    :class:`~ape.plugins.project.ProjectPlugin` implementations.
    """

    @hookspec
    def dependencies(self) -> Dict[str, Type[DependencyAPI]]:
        """
        A hook that returns a :class:`~ape.api.projects.DependencyAPI` mapped
        to its ``ape-config.yaml`` file dependencies special key. For example,
        when configuring GitHub dependencies, you set the ``github`` key in
        the ``dependencies:`` block of your ``ape-config.yaml`` file and it
        will automatically use this ``DependencyAPI`` implementation.

        Returns:
            Type[:class:`~ape.api.projects.DependencyAPI`]
        """
