from typing import Iterator, Tuple, Type

from ape.api import EcosystemAPI, ExplorerAPI, NetworkAPI, ProviderAPI

from .pluggy_patch import PluginType, hookspec


class EcosystemPlugin(PluginType):
    @hookspec
    def ecosystems(self) -> Iterator[Type[EcosystemAPI]]:
        """
        Must return an iterator of EcosystemAPI subclasses
        """


class NetworkPlugin(PluginType):
    @hookspec
    def networks(self) -> Iterator[Tuple[str, str, Type[NetworkAPI]]]:
        """
        Must return an iterator of tuples of:
            the target Ecosystem plugin's name
            the Network name
            a NetworkAPI subclass
        """


class ProviderPlugin(PluginType):
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
