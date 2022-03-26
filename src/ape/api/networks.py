from functools import partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Type

from ethpm_types.abi import ConstructorABI, EventABI, MethodABI
from hexbytes import HexBytes

from ape.exceptions import NetworkError, NetworkNotFoundError
from ape.types import AddressType, ContractLog
from ape.utils import BaseInterfaceModel, abstractmethod, cached_property

from .config import PluginConfig

if TYPE_CHECKING:
    from ape.managers.networks import NetworkManager

    from .explorers import ExplorerAPI
    from .providers import BlockAPI, ProviderAPI, ReceiptAPI, TransactionAPI


LOCAL_NETWORK_NAME = "local"


class EcosystemAPI(BaseInterfaceModel):
    """
    A set of related networks, such as Ethereum.
    """

    name: str
    """
    The name of the ecosystem. This should be set the same name as the plugin.
    """

    data_folder: Path
    """The path to the ``.ape`` directory."""

    request_header: dict
    """A shareable HTTP header for network requests."""

    _default_network: str = LOCAL_NETWORK_NAME

    @abstractmethod
    def serialize_transaction(self, transaction: "TransactionAPI") -> bytes:
        """
        Serialize a transaction to bytes.

        Args:
            transaction (:class:`~ape.api.providers.TransactionAPI`): The transaction to encode.

        Returns:
            bytes
        """

    @abstractmethod
    def decode_receipt(self, data: dict) -> "ReceiptAPI":
        """
        Convert data to :class:`~ape.api.providers.ReceiptAPI`.

        Args:
            data (dict): A dictionary of Receipt properties.

        Returns:
            :class:`~ape.api.providers.ReceiptAPI`
        """

    @abstractmethod
    def decode_block(self, data: dict) -> "BlockAPI":
        """
        Decode data to a :class:`~ape.api.providers.BlockAPI`.

        Args:
            data (dict): A dictionary of data to decode.

        Returns:
            :class:`~ape.api.providers.BlockAPI`
        """

    @cached_property
    def config(self) -> PluginConfig:
        """
        The configuration of the ecosystem. See :class:`ape.managers.config.ConfigManager`
        for more information on plugin configurations.

        Returns:
            :class:`ape.api.config.PluginConfig`
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
        return self.get_network(network_name)

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
        return self.get_network(network_name)

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
        self, deployment_bytecode: HexBytes, abi: ConstructorABI, *args, **kwargs
    ) -> "TransactionAPI":
        ...

    @abstractmethod
    def encode_transaction(
        self, address: AddressType, abi: MethodABI, *args, **kwargs
    ) -> "TransactionAPI":
        ...

    @abstractmethod
    def decode_logs(self, abi: EventABI, raw_logs: List[Dict]) -> Iterator[ContractLog]:
        ...

    @abstractmethod
    def create_transaction(self, **kwargs) -> "TransactionAPI":
        ...

    def get_network(self, network_name: str) -> "NetworkAPI":
        """
        Get the network for the given name.

        Args:
              network_name (str): The name of the network to get.

        Raises:
              :class:`~ape.exceptions.NetworkNotFoundError`: When the network is not present.

        Returns:
              :class:`~ape.api.networks.NetworkAPI`
        """

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
    network_manager: "NetworkManager"

    def __init__(self, provider: "ProviderAPI", network_manager: "NetworkManager"):
        self.provider = provider
        self.network_manager = network_manager

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

        # NOTE: using id() to prevent pydantic recursive serialization
        if id(self.provider) != id(provider):
            raise ValueError("Previous provider value unknown.")

        provider.disconnect()

        if self._connected_providers:
            self._connected_providers[-1].connect()
            self.network_manager.active_provider = self._connected_providers[-1]


class NetworkAPI(BaseInterfaceModel):
    """
    A wrapper around a provider for a specific ecosystem.
    """

    name: str  # Name given when registered in ecosystem
    """The name of the network."""

    ecosystem: EcosystemAPI
    """The ecosystem of the network."""

    data_folder: Path  # For caching any data that might need caching
    """The path to the ``.ape`` directory."""

    request_header: dict
    """A shareable network HTTP header."""

    _default_provider: str = ""

    @cached_property
    def config(self) -> PluginConfig:
        """
        The configuration of the network. See :class:`~ape.managers.config.ConfigManager`
        for more information on plugin configurations.
        """

        return self.config_manager.get_config(self.ecosystem.name)

    @cached_property
    def _network_config(self) -> PluginConfig:
        return self.config.dict().get(self.name, {})  # type: ignore

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
        return self._network_config.get("required_confirmations", 0)  # type: ignore

    @property
    def block_time(self) -> int:
        """
        The approximate amount of time it takes for a new block to get mined to the chain.
        Configure in your ``ape-config.yaml`` file.

        Config example::

            ethereum:
              mainnet:
                block_time: 15

        Returns:
            int
        """

        return self._network_config.get("block_time", 0)  # type: ignore

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
                )

        return None  # May not have an block explorer

    @cached_property
    def providers(self):  # -> Dict[str, Partial[ProviderAPI]]
        """
        The providers of the network, such as Infura, Alchemy, or Geth.

        Returns:
            Dict[str, partial[:class:`~ape.api.providers.ProviderAPI`]]
        """

        from ape.plugins import clean_plugin_name

        providers = {}

        for plugin_name, plugin_tuple in self.plugin_manager.providers:
            ecosystem_name, network_name, provider_class = plugin_tuple
            provider_name = clean_plugin_name(provider_class.__module__.split(".")[0])

            if self.ecosystem.name == ecosystem_name and self.name == network_name:
                # NOTE: Lazily load provider config
                providers[provider_name] = partial(
                    provider_class,
                    name=provider_name,
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
            provider_settings (dict, optional): Settings to apply to the provider. Defaults to
              ``None``.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`
        """

        provider_name = provider_name or self.default_provider or ""
        provider_settings = provider_settings or {}

        if ":" in provider_name:
            # NOTE: Shortcut that allows `--network ecosystem:network:http://...` to work
            provider_settings["uri"] = provider_name
            provider_name = provider_name.split(":")[0]

        if provider_name in self.providers:
            return self.providers[provider_name](provider_settings=provider_settings)

        else:
            message = (
                f"'{provider_name}' is not a valid provider for ecosystem '{self.ecosystem.name}'"
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
            provider=self.get_provider(
                provider_name=provider_name, provider_settings=provider_settings
            ),
            network_manager=self.network_manager,
        )

    @property
    def default_provider(self) -> Optional[str]:
        """
        The name of the default provider or ``None``.

        Returns:
            Optional[str]
        """

        if self._default_provider:
            return self._default_provider

        if len(self.providers) > 0:
            return list(self.providers)[0]

        return None

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
        if self.default_provider:
            return self.use_provider(self.default_provider, provider_settings=provider_settings)

        raise NetworkError(f"No providers for network '{self.name}'.")


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
