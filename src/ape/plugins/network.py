from typing import Iterator, Tuple, Type

from ape.api import EcosystemAPI, ExplorerAPI, NetworkAPI, ProviderAPI

from .pluggy_patch import PluginType, hookspec


class EcosystemPlugin(PluginType):
    """
    An ecosystem plugin, such as `ape-ethereum`. See the
    :class:`ape.api.networks.EcosystemAPI` for more information on
    what is required to implement this type of plugin.
    """

    @hookspec
    def ecosystems(self) -> Iterator[Type[EcosystemAPI]]:
        """
        A hook that must return an iterator of :class:`ape.api.networks.EcosystemAPI`
        subclasses.

        Returns:
            iter[type[:class:`~ape.api.networks.EcosystemAPI`]]
        """


class NetworkPlugin(PluginType):
    """
    A network plugin, such as `mainnet` or `ropsten`. Likely, registering networks
    will happen soon after registering the ecosystem, as an ecosystem requires
    networks.
    """

    @hookspec
    def networks(self) -> Iterator[Tuple[str, str, Type[NetworkAPI]]]:
        """
        A hook that must return an iterator of tuples of:
            * the target Ecosystem plugin's name
            * the Network name
            * a :class:`ape.api.networks.NetworkAPI` subclass

        Returns:
            iter[tuple[str, str, type[:class:`~ape.api.networks.NetworkAPI`]]]
        """


class ProviderPlugin(PluginType):
    """
    A plugin representing a blockchain provider, which is the API responsible
    for interacting with the blockchain, such as making network requests.
    Example provider plugins would be
    """

    @hookspec
    def providers(self) -> Iterator[Tuple[str, str, Type[ProviderAPI]]]:
        """
        Must return an iterator of tuples of:
            the target Ecosystem plugin's name
            the Network it works with (which must be valid Network in the Ecosystem)
            a ProviderAPI subclass
        """


class ExplorerPlugin(PluginType):
    @hookspec
    def explorers(self) -> Iterator[Tuple[str, str, Type[ExplorerAPI]]]:
        """
        Must return an iterator of tuples of:
            the target Ecosystem plugin's name
            the Network it works with (which must be valid Network in the Ecosystem)
            a ExplorerAPI subclass
        """
