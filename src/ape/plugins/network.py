from collections.abc import Iterator

from ape.api.explorers import ExplorerAPI
from ape.api.networks import EcosystemAPI, NetworkAPI
from ape.api.providers import ProviderAPI

from .pluggy_patch import PluginType, hookspec


class EcosystemPlugin(PluginType):
    """
    An ecosystem plugin, such as ``ape-ethereum``. See the
    :class:`ape.api.networks.EcosystemAPI` for more information on
    what is required to implement an ecosystem plugin.
    """

    @hookspec  # type: ignore[empty-body]
    def ecosystems(self) -> Iterator[type[EcosystemAPI]]:
        """
        A hook that must return an iterator of :class:`ape.api.networks.EcosystemAPI`
        subclasses.

        Usage example::

            @plugins.register(plugins.EcosystemPlugin)
            def ecosystems():
                yield Ethereum

        Returns:
            Iterator[type[:class:`~ape.api.networks.EcosystemAPI`]]
        """


class NetworkPlugin(PluginType):
    """
    A network plugin, such as ``mainnet`` or ``ropsten``. Likely, registering networks
    will happen soon after registering the ecosystem, as an ecosystem requires
    networks.
    """

    @hookspec  # type: ignore[empty-body]
    def networks(self) -> Iterator[tuple[str, str, type[NetworkAPI]]]:
        """
        A hook that must return an iterator of tuples of:

        * the target ecosystem plugin's name
        * the network name
        * a :class:`ape.api.networks.NetworkAPI` subclass

        Usage example::

            @plugins.register(plugins.NetworkPlugin)
            def networks():
                yield "ethereum", "ShibaChain", ShibaNetwork

        Returns:
            Iterator[tuple[str, str, type[:class:`~ape.api.networks.NetworkAPI`]]]
        """


class ProviderPlugin(PluginType):
    """
    A plugin representing a network provider, which is the main API responsible
    for making requests against a blockchain. Example provider plugins projects
    include `ape-infura <https://github.com/ApeWorX/ape-infura>`__ as well as
    `ape-alchemy <https://github.com/ApeWorX/ape-alchemy>`__.
    """

    @hookspec
    def providers(self) -> Iterator[tuple[str, str, type[ProviderAPI]]]:  # type: ignore[empty-body]
        """
        A hook that must return an iterator of tuples of:

        * the target ecosystem plugin's name
        * the network it works with (which must be valid network in the ecosystem)
        * a :class:`ape.api.providers.ProviderAPI` subclass

        Usage example::

            @plugins.register(plugins.ProviderPlugin)
            def providers():
                yield "ethereum", "local", MyProvider

        Returns:
            Iterator[tuple[str, str, type[:class:`~ape.api.providers.ProviderAPI`]]]
        """


class ExplorerPlugin(PluginType):
    """
    A plugin for a blockchain explorer, such as
    `ape-etherscan <https://github.com/ApeWorX/ape-etherscan>`__.
    """

    @hookspec
    def explorers(self) -> Iterator[tuple[str, str, type[ExplorerAPI]]]:  # type: ignore[empty-body]
        """
        A hook that must return an iterator of tuples of:

        * the target ecosystem plugin's name
        * the network it works with (which must be valid network in the ecosystem)
        * a :class:`~ape.api.explorers.ExplorerAPI` subclass

        Usage example::

            @plugins.register(plugins.ExplorerPlugin)
            def explorers():
                yield "ethereum", "mainnet", MyBlockExplorer

        Returns:
            Iterator[tuple[str, str, type[:class:`ape.api.explorers.ExplorerAPI`]]]
        """
