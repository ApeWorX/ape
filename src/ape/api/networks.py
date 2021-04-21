from abc import ABCMeta, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING, Callable, Dict, Iterator, Optional, Type

from dataclassy import dataclass
from pluggy import PluginManager  # type: ignore

from ape.utils import cached_property

if TYPE_CHECKING:
    from .explorers import ExplorerAPI
    from .providers import ProviderAPI


@dataclass
class EcosystemAPI:
    """
    An Ecosystem is a set of related Networks
    """

    name: str  # Set as plugin name
    plugin_manager: PluginManager
    data_folder: Path
    request_header: str

    _default_network: str = "development"

    @cached_property
    def networks(self) -> Dict[str, "NetworkAPI"]:
        networks = {}
        for _, (ecosystem_name, network_name, network_class) in self.plugin_manager.networks:
            if ecosystem_name == self.name:
                network_folder = self.data_folder / network_name

                networks[network_name] = network_class(
                    name=network_name,
                    ecosystem=self,
                    plugin_manager=self.plugin_manager,
                    data_folder=network_folder,
                    request_header=self.request_header,
                )

        if len(networks) > 0:
            return networks

        else:
            raise  # No networks found!

    def __init__(self):
        if len(self.networks) == 0:
            raise  # Must define at least one network in ecosystem

    def __iter__(self) -> Iterator[str]:
        """
        Provides the set of all valid Network names in the ecosystem
        """
        for name in self.networks:
            yield name

    def __getitem__(self, network_name: str) -> "NetworkAPI":
        if network_name in self.networks:
            return self.networks[network_name]

        else:
            raise  # No network with name

    def __getattr__(self, network_name: str) -> "NetworkAPI":
        if network_name in self.networks:
            return self.networks[network_name]

        else:
            raise  # No network with name

    def add_network(self, network_name: str, network: "NetworkAPI"):
        """
        Used to attach new networks to an ecosystem (e.g. L2 networks like Optimism)
        """
        if network_name in self.networks:
            raise  # Can't overwrite an existing network!
        else:
            self.networks[network_name] = network

    @property
    def default_network(self) -> str:
        return self._default_network

    def set_default_network(self, network_name: str):
        if network_name in self.networks:
            self._default_network = network_name
        else:
            raise  # Not a valid network for ecosystem `self.name`


class ProviderContextManager:
    def __init__(self, provider: "ProviderAPI"):
        self.provider = provider

    def __enter__(self, *args, **kwargs):
        self.provider.connect()
        return self.provider

    def __exit__(self, *args, **kwargs):
        self.provider.disconnect()


@dataclass
class NetworkAPI(metaclass=ABCMeta):
    """
    A Network is a wrapper around a Provider for a specific Ecosystem
    """

    name: str  # Name given when regsitered in ecosystem
    ecosystem: EcosystemAPI
    plugin_manager: PluginManager
    data_folder: Path  # For caching any data that might need caching
    request_header: str

    _default_provider: str = ""

    @property
    @abstractmethod
    def chain_id(self) -> int:
        ...

    @property
    @abstractmethod
    def network_id(self) -> int:
        ...

    @cached_property
    def explorer(self) -> Optional["ExplorerAPI"]:
        for plugin_name, plugin_tuple in self.plugin_manager.explorers:
            ecosystem_name, network_name, explorer_class = plugin_tuple

            if self.ecosystem.name == ecosystem_name and self.name == network_name:
                # Return the first registered explorer (skipping any others)
                return explorer_class(
                    name=plugin_name,
                    network=self,
                    request_header=self.request_header,
                )

        return None  # May not have an block explorer

    @cached_property
    def providers(self) -> Dict[str, Callable[[dict], "ProviderAPI"]]:  # noqa: F811
        providers = {}

        for plugin_name, plugin_tuple in self.plugin_manager.providers:
            ecosystem_name, network_name, provider_class = plugin_tuple

            if self.ecosystem.name == ecosystem_name and self.name == network_name:
                # NOTE: Lazily load and provider config on load
                providers[plugin_name] = lambda config: provider_class(
                    name=plugin_name,
                    network=self,
                    config=config,
                    # NOTE: No need to have separate folder, caching should be interoperable
                    data_folder=self.data_folder,
                    request_header=self.request_header,
                )

        if len(providers) > 0:
            return providers

        else:
            raise  # No providers found

    def use_provider(
        self,
        provider_name: str,
        provider_settings: dict = None,
    ) -> ProviderContextManager:
        if provider_settings is None:
            provider_settings = {}

        if ":" in provider_name:
            # NOTE: Shortcut that allows `--network ecosystem:network:http://...` to work
            provider_settings["uri"] = provider_name
            provider_name = provider_name.split(":")[0]

        if provider_name in self.providers:
            return ProviderContextManager(self.providers[provider_name](provider_settings))

        else:
            raise  # Not a registered provider name

    @property
    def default_provider(self) -> str:
        return self._default_provider or list(self.providers)[0]

    def set_default_provider(self, provider_name: str):
        if provider_name in self.providers:
            self._default_provider = provider_name
        else:
            raise  # Not a valid provider for network `self.name`

    def use_default_provider(self) -> ProviderContextManager:
        # NOTE: If multiple providers, use whatever is "first" registered
        return self.use_provider(self.default_provider)


def create_network_type(chain_id: int, network_id: int) -> Type[NetworkAPI]:
    """
    Helper function that allows creating a `NetworkAPI` subclass easily
    """

    class network_def(NetworkAPI):
        def chain_id(self) -> int:
            return chain_id

        def network_id(self) -> int:
            return network_id

    return network_def
