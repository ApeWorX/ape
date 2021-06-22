from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Dict, Iterator, List, Optional, Type

from pluggy import PluginManager  # type: ignore

from ape.types import ABI
from ape.utils import cached_property

from .base import abstractdataclass, abstractmethod

if TYPE_CHECKING:
    from ape.managers.networks import NetworkManager

    from .contracts import ContractLog
    from .explorers import ExplorerAPI
    from .providers import ProviderAPI, ReceiptAPI, TransactionAPI


@abstractdataclass
class EcosystemAPI:
    """
    An Ecosystem is a set of related Networks
    """

    name: str  # Set as plugin name
    network_manager: "NetworkManager"
    plugin_manager: PluginManager
    data_folder: Path
    request_header: str

    transaction_class: Type["TransactionAPI"]
    receipt_class: Type["ReceiptAPI"]

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
            raise Exception("No networks found!")

    def __post_init__(self):
        if len(self.networks) == 0:
            raise Exception("Must define at least one network in ecosystem")

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
            raise Exception("No network with name")

    def __getattr__(self, network_name: str) -> "NetworkAPI":
        if network_name in self.networks:
            return self.networks[network_name]

        else:
            raise Exception("No network with name")

    def add_network(self, network_name: str, network: "NetworkAPI"):
        """
        Used to attach new networks to an ecosystem (e.g. L2 networks like Optimism)
        """
        if network_name in self.networks:
            raise Exception("Can't overwrite an existing network!")
        else:
            self.networks[network_name] = network

    @property
    def default_network(self) -> str:
        return self._default_network

    def set_default_network(self, network_name: str):
        if network_name in self.networks:
            self._default_network = network_name
        else:
            raise Exception("Not a valid network for ecosystem `self.name`")

    @abstractmethod
    def encode_deployment(
        self, deployment_bytecode: bytes, abi: Optional[ABI], *args, **kwargs
    ) -> "TransactionAPI":
        ...

    @abstractmethod
    def encode_transaction(self, address: str, abi: ABI, *args, **kwargs) -> "TransactionAPI":
        ...

    @abstractmethod
    def decode_event(self, abi: ABI, receipt: "ReceiptAPI") -> "ContractLog":
        ...


class ProviderContextManager:
    # NOTE: Class variable, so it will manage stack across instances of this object
    _connected_providers: List["ProviderAPI"] = []

    def __init__(self, network_manager: "NetworkManager", provider: "ProviderAPI"):
        self.network_manager = network_manager
        self.provider = provider

    def __enter__(self, *args, **kwargs):
        # If we are already connected to a provider, disconnect and add
        # it to our stack of providers that were connected
        if self._connected_providers:
            self._connected_providers[-1].disconnect()

        # Connect to our provider
        self.provider.connect()
        self.network_manager.active_provider = self.provider
        self._connected_providers.append(self.provider)

        return self.provider

    def __exit__(self, *args, **kwargs):
        # Put our providers back the way it was
        provider = self._connected_providers.pop()
        assert self.provider == provider
        provider.disconnect()

        if self._connected_providers:
            self._connected_providers[-1].connect()
            self.network_manager.active_provider = self._connected_providers[-1]


@abstractdataclass
class NetworkAPI:
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
    def providers(self):  # -> Dict[str, Partial[ProviderAPI]]
        providers = {}

        for plugin_name, plugin_tuple in self.plugin_manager.providers:
            ecosystem_name, network_name, provider_class = plugin_tuple

            if self.ecosystem.name == ecosystem_name and self.name == network_name:
                # NOTE: Lazily load and provider config on load
                providers[plugin_name] = partial(
                    provider_class,
                    name=plugin_name,
                    network=self,
                    # NOTE: No need to have separate folder, caching should be interoperable
                    data_folder=self.data_folder,
                    request_header=self.request_header,
                )

        if len(providers) > 0:
            return providers

        else:
            raise Exception("No providers found")

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
            return ProviderContextManager(
                self.ecosystem.network_manager,
                self.providers[provider_name](config=provider_settings),
            )

        else:
            raise Exception("Not a registered provider name")

    @property
    def default_provider(self) -> str:
        return self._default_provider or list(self.providers)[0]

    def set_default_provider(self, provider_name: str):
        if provider_name in self.providers:
            self._default_provider = provider_name
        else:
            raise Exception("Not a valid provider for network `self.name`")

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
