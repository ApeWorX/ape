from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Type

from pluggy import PluginManager  # type: ignore

from ape.exceptions import NetworkError, NetworkNotFoundError
from ape.types import ABI, AddressType
from ape.utils import abstractdataclass, abstractmethod, cached_property, dataclass

from .config import ConfigItem

if TYPE_CHECKING:
    from ape.contracts import ContractLog
    from ape.managers.config import ConfigManager
    from ape.managers.networks import NetworkManager

    from .explorers import ExplorerAPI
    from .providers import BlockAPI, ProviderAPI, ReceiptAPI, TransactionAPI, TransactionType


@abstractdataclass
class EcosystemAPI:
    """
    A set of related networks, such as Ethereum.
    """

    name: str
    """
    The name of the ecosystem. This should be set the same name as the plugin.
    """

    network_manager: "NetworkManager"
    """A reference to the global network manager."""

    config_manager: "ConfigManager"
    """A reference to the global config manager."""

    plugin_manager: PluginManager
    """A reference to the global plugin manager."""

    data_folder: Path
    """The path to the ``.ape`` directory."""

    request_header: str
    """A shareable HTTP header for network requests."""

    transaction_types: Dict["TransactionType", Type["TransactionAPI"]]
    """The available types of transaction API this ecosystem supports."""

    receipt_class: Type["ReceiptAPI"]
    """The receipt class for this ecosystem."""

    block_class: Type["BlockAPI"]
    """The block class for this ecosystem."""

    _default_network: str = "development"

    @cached_property
    def config(self) -> ConfigItem:
        """
        The configuration of the ecosystem. See :class:`ape.managers.config.ConfigManager`
        for more information on plugin configurations.

        Returns:
            :class:`ape.api.config.ConfigItem`
        """

        return self.config_manager.get_config(self.name)

    @cached_property
    def networks(self) -> Dict[str, "NetworkAPI"]:
        """
        A dictionary of network names mapped to their API implementation.

        Returns:
            Dict[str, :class:`~ape.api.networks.NetworkAPI`]
        """

        networks = {}
        for _, (ecosystem_name, network_name, network_class) in self.plugin_manager.networks:
            if ecosystem_name == self.name:
                network_folder = self.data_folder / network_name

                networks[network_name] = network_class(
                    name=network_name,
                    ecosystem=self,
                    config_manager=self.config_manager,
                    plugin_manager=self.plugin_manager,
                    data_folder=network_folder,
                    request_header=self.request_header,
                )

        if len(networks) > 0:
            return networks

        else:
            raise NetworkError("No networks found")

    def __post_init__(self):
        if len(self.networks) == 0:
            raise NetworkError("Must define at least one network in ecosystem")

    def __iter__(self) -> Iterator[str]:
        """
        Iterate over the set of all valid network names in the ecosystem.

        Returns:
            Iterator[str]
        """
        yield from self.networks

    def __getitem__(self, network_name: str) -> "NetworkAPI":
        """
        Get a network by name.

        Raises:
            :class:`~ape.exceptions.NetworkNotFoundError`:
              When there is no network with the given name.

        Args:
            network_name (str): The name of the network to retrieve.

        Returns:
            :class:`~ape.api.networks.NetworkAPI`
        """

        return self._try_get_network(network_name)

    def __getattr__(self, network_name: str) -> "NetworkAPI":
        """
        Get a network by name using ``.`` access.

        Usage example::

            from ape import networks
            mainnet = networks.ecosystem.mainnet

        Raises:
            :class:`~ape.exceptions.NetworkNotFoundError`:
              When there is no network with the given name.

        Args:
            network_name (str): The name of the network to retrieve.

        Returns:
            :class:`~ape.api.networks.NetworkAPI`
        """

        network_name = network_name.replace("_", "-")
        return self._try_get_network(network_name)

    def add_network(self, network_name: str, network: "NetworkAPI"):
        """
        Attach a new network to an ecosystem (e.g. L2 networks like Optimism).

        Raises:
            :class:`ape.exceptions.NetworkError`: When the network already exists.

        Args:
            network_name (str): The name of the network to add.

        Returns:
            :class:`~ape.api.networks.NetworkAPI`
        """
        if network_name in self.networks:
            raise NetworkError(f"Unable to overwrite existing network '{network_name}'.")
        else:
            self.networks[network_name] = network

    @property
    def default_network(self) -> str:
        """
        The name of the default network in this ecosystem.

        Returns:
            str
        """

        return self._default_network

    def set_default_network(self, network_name: str):
        """
        Change the default network.

        Raises:
            :class:`~ape.exceptions.NetworkError`: When the network does not exist.

        Args:
            network_name (str): The name of the default network to switch to.
        """

        if network_name in self.networks:
            self._default_network = network_name
        else:
            message = f"'{network_name}' is not a valid network for ecosystem '{self.name}'."
            raise NetworkError(message)

    @abstractmethod
    def encode_deployment(
        self, deployment_bytecode: bytes, abi: Optional[ABI], *args, **kwargs
    ) -> "TransactionAPI":
        ...

    @abstractmethod
    def encode_transaction(
        self, address: AddressType, abi: ABI, *args, **kwargs
    ) -> "TransactionAPI":
        ...

    @abstractmethod
    def decode_event(self, abi: ABI, receipt: "ReceiptAPI") -> "ContractLog":
        ...

    @abstractmethod
    def create_transaction(self, **kwargs) -> "TransactionAPI":
        ...

    def _try_get_network(self, network_name):
        if network_name in self.networks:
            return self.networks[network_name]
        else:
            raise NetworkNotFoundError(network_name)

    def get_network_data(self, network_name: str) -> Dict:
        """
        Get a dictionary of data about providers in the network.

        **NOTE**: The keys are added in an opinionated order for nicely
        translating into ``yaml``.

        Args:
            network_name (str): The name of the network to get provider data from.

        Returns:
            dict: A dictionary containing the providers in a network.
        """
        data: Dict[str, Any] = {"name": network_name}

        # Only add isDefault key when True
        if network_name == self.default_network:
            data["isDefault"] = True

        data["providers"] = []
        network = self[network_name]
        if network.explorer:
            data["explorer"] = network.explorer.name

        for provider_name in network.providers:
            provider_data = {"name": provider_name}

            # Only add isDefault key when True
            if provider_name == network.default_provider:
                provider_data["isDefault"] = True

            data["providers"].append(provider_data)

        return data


class ProviderContextManager:
    """
    A context manager for temporarily connecting to a network.
    When entering the context, calls the :meth:`ape.api.providers.ProviderAPI.connect` method.
    And conversely, when exiting, calls the :meth:`ape.api.providers.ProviderPAI.disconnect`
    method.

    The method :meth:`ape.api.networks.NetworkAPI.use_provider` returns
    an instance of this context manager.

    Usage example::

        from ape import networks

        mainnet = networks.ethereum.mainnet  # An instance of NetworkAPI
        with mainnet.use_provider("infura"):
            ...
    """

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
        if self.provider != provider:
            raise ValueError("Previous provider value unknown.")

        provider.disconnect()

        if self._connected_providers:
            self._connected_providers[-1].connect()
            self.network_manager.active_provider = self._connected_providers[-1]


@dataclass
class NetworkAPI:
    """
    A wrapper around a provider for a specific ecosystem.
    """

    name: str  # Name given when registered in ecosystem
    """The name of the network."""

    ecosystem: EcosystemAPI
    """The ecosystem of the network."""

    config_manager: "ConfigManager"
    """A reference to the global config manager."""

    plugin_manager: PluginManager
    """A reference to the global plugin manager."""

    data_folder: Path  # For caching any data that might need caching
    """The path to the ``.ape`` directory."""

    request_header: str
    """A shareable network HTTP header."""

    _default_provider: str = ""

    @cached_property
    def config(self) -> ConfigItem:
        """
        The configuration of the network. See :class:`~ape.managers.config.ConfigManager`
        for more information on plugin configurations.
        """

        return self.config_manager.get_config(self.ecosystem.name)

    @property
    def chain_id(self) -> int:
        """
        The ID of the blockchain.

        **NOTE**: Unless overridden, returns same as
        :py:attr:`ape.api.providers.ProviderAPI.chain_id`.

        Returns:
            int
        """

        provider = self.ecosystem.network_manager.active_provider

        if not provider:
            message = (
                "Cannot determine 'chain_id', please make sure you are connected to a provider."
            )
            raise NetworkError(message)

        return provider.chain_id

    @property
    def network_id(self) -> int:
        """
        The ID of the network.

        **NOTE**: Unless overridden, returns same as
        :py:attr:`~ape.api.networks.NetworkAPI.chain_id`.

        Returns:
            int
        """
        return self.chain_id

    @property
    def required_confirmations(self) -> int:
        """
        The default amount of confirmations recommended to wait
        before considering a transaction "confirmed". Confirmations
        refer to the number of blocks that have been added since the
        transaction's block.

        Returns:
            int
        """
        try:
            return self.config[self.name]["required_confirmations"]
        except KeyError:
            # Is likely a 'development' network.
            return 0

    @cached_property
    def explorer(self) -> Optional["ExplorerAPI"]:
        """
        The block-explorer for the given network.

        Returns:
            :class:`ape.api.explorers.ExplorerAPI`, optional
        """

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
        """
        The providers of the network, such as Infura, Alchemy, or Geth.

        Returns:
            Dict[str, partial[:class:`~ape.api.providers.ProviderAPI`]]
        """

        providers = {}

        for plugin_name, plugin_tuple in self.plugin_manager.providers:
            ecosystem_name, network_name, provider_class = plugin_tuple

            if self.ecosystem.name == ecosystem_name and self.name == network_name:
                # NOTE: Lazily load and provider config on load
                providers[plugin_name] = partial(
                    provider_class,
                    name=plugin_name,
                    config=self.config_manager.get_config(plugin_name),
                    network=self,
                    # NOTE: No need to have separate folder, caching should be interoperable
                    data_folder=self.data_folder,
                    request_header=self.request_header,
                )

        return providers

    def get_provider(
        self,
        provider_name: Optional[str] = None,
        provider_settings: dict = None,
    ):
        """
        Get a provider for the given name. If given ``None``, returns the default provider.

        Args:
            provider_name (str, optional): The name of the provider to get. Defaults to ``None``.
              When ``None``, returns the default provider.
            provider_settings dict, optional): Settings to apply to the provider. Defaults to
              ``None``.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`
        """

        provider_name = provider_name or self.default_provider
        provider_settings = provider_settings or {}

        if ":" in provider_name:
            # NOTE: Shortcut that allows `--network ecosystem:network:http://...` to work
            provider_settings["uri"] = provider_name
            provider_name = provider_name.split(":")[0]

        if provider_name in self.providers:
            return self.providers[provider_name](provider_settings=provider_settings)

        else:
            message = (
                f"'{provider_name}' is not a valid network for ecosystem '{self.ecosystem.name}'"
            )
            raise NetworkError(message)

    def use_provider(
        self,
        provider_name: str,
        provider_settings: dict = None,
    ) -> ProviderContextManager:
        """
        Use and connect to a provider in a temporary context. When entering the context, it calls
        method :meth:`ape.api.providers.ProviderAPI.connect` and when exiting, it calls
        method :meth:`ape.api.providers.ProviderAPI.disconnect`.

        Usage example::

            from ape import networks

            mainnet = networks.ethereum.mainnet  # An instance of NetworkAPI
            with mainnet.use_provider("infura"):
                ...

        Args:
            provider_name (str): The name of the provider to use.
            provider_settings (dict, optional): Settings to apply to the provider.
              Defaults to ``None``.

        Returns:
            :class:`ape.api.networks.ProviderContextManager`
        """

        return ProviderContextManager(
            self.ecosystem.network_manager,
            self.get_provider(provider_name=provider_name, provider_settings=provider_settings),
        )

    @property
    def default_provider(self) -> str:
        """
        The name of the default provider.

        Returns:
            str
        """

        return self._default_provider or list(self.providers)[0]

    def set_default_provider(self, provider_name: str):
        """
        Change the default provider.

        Raises:
            :class:`~ape.exceptions.NetworkError`: When the given provider is not found.

        Args:
            provider_name (str): The name of the provider to switch to.
        """

        if provider_name in self.providers:
            self._default_provider = provider_name
        else:
            raise NetworkError(f"No providers found for network '{self.name}'")

    def use_default_provider(self, provider_settings: Optional[Dict]) -> ProviderContextManager:
        """
        Temporarily connect and use the default provider. When entering the context, it calls
        method :meth:`ape.api.providers.ProviderAPI.connect` and when exiting, it calls
        method :meth:`ape.api.providers.ProviderAPI.disconnect`.

        **NOTE**: If multiple providers exist, uses whatever was "first" registered.

        Usage example::

            from ape import networks
            mainnet = networks.ethereum.mainnet  # An instance of NetworkAPI
            with mainnet.use_default_provider():
                ...

        Args:
            provider_settings (dict, optional): Settings to override the provider.

        Returns:
            :class:`~ape.api.networks.ProviderContextManager`
        """
        return self.use_provider(self.default_provider, provider_settings=provider_settings)


def create_network_type(chain_id: int, network_id: int) -> Type[NetworkAPI]:
    """
    Easily create a :class:`ape.api.networks.NetworkAPI` subclass.
    """

    class network_def(NetworkAPI):
        @property
        def chain_id(self) -> int:
            return chain_id

        @property
        def network_id(self) -> int:
            return network_id

    return network_def
