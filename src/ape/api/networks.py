from functools import partial
from pathlib import Path
from tempfile import mkdtemp
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Optional, Tuple, Type, Union

from eth_account import Account as EthAccount
from eth_account._utils.legacy_transactions import (
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_utils import keccak, to_int
from ethpm_types.abi import ConstructorABI, EventABI, MethodABI
from hexbytes import HexBytes
from pydantic import BaseModel

from ape.exceptions import (
    NetworkError,
    NetworkMismatchError,
    NetworkNotFoundError,
    ProviderNotConnectedError,
    SignatureError,
)
from ape.logging import logger
from ape.types import AddressType, CallTreeNode, ContractLog, GasLimit, RawAddress
from ape.utils import (
    DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT,
    BaseInterfaceModel,
    ManagerAccessMixin,
    abstractmethod,
    cached_property,
    raises_not_implemented,
)

from .config import PluginConfig

if TYPE_CHECKING:
    from .explorers import ExplorerAPI
    from .providers import BlockAPI, ProviderAPI
    from .transactions import ReceiptAPI, TransactionAPI


LOCAL_NETWORK_NAME = "local"


class ProxyInfoAPI(BaseModel):
    """
    Information about a proxy contract.
    """

    target: AddressType
    """The address of the implementation contract."""


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

    fee_token_symbol: str
    """The token symbol for the currency that pays for fees, such as ETH."""

    _default_network: str = LOCAL_NETWORK_NAME

    def __repr__(self) -> str:
        return f"<{self.name}>"

    @classmethod
    @abstractmethod
    def decode_address(cls, raw_address: RawAddress) -> AddressType:
        """
        Convert a raw address to the ecosystem's native address type.

        Args:
            raw_address (Union[str, int]): The address to convert.

        Returns:
            ``AddressType``
        """

    @classmethod
    @abstractmethod
    def encode_address(cls, address: AddressType) -> RawAddress:
        """
        Convert the ecosystem's native address type to a raw integer or str address.

        Args:
            address (Union[str, int]): The address to convert.

        Returns:
            Union[str, int]
        """

    def serialize_transaction(self, transaction: "TransactionAPI") -> bytes:
        """
        Serialize a transaction to bytes.

        Args:
            transaction (:class:`~ape.api.transactions.TransactionAPI`): The transaction to encode.

        Returns:
            bytes
        """

        if not self.signature:
            raise SignatureError("The transaction is not signed.")

        txn_data = self.dict(exclude={"sender"})

        unsigned_txn = serializable_unsigned_transaction_from_dict(txn_data)
        signature = (
            self.signature.v,  # type: ignore
            to_int(self.signature.r),  # type: ignore
            to_int(self.signature.s),  # type: ignore
        )

        signed_txn = encode_transaction(unsigned_txn, signature)

        if self.sender and EthAccount.recover_transaction(signed_txn) != self.sender:
            raise SignatureError("Recovered signer doesn't match sender!")

        return signed_txn

    @abstractmethod
    def decode_receipt(self, data: dict) -> "ReceiptAPI":
        """
        Convert data to :class:`~ape.api.transactions.ReceiptAPI`.

        Args:
            data (dict): A dictionary of Receipt properties.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`
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
        try:
            return self.get_network(network_name.replace("_", "-"))
        except NetworkNotFoundError:
            return self.__getattribute__(network_name)

    def add_network(self, network_name: str, network: "NetworkAPI"):
        """
        Attach a new network to an ecosystem (e.g. L2 networks like Optimism).

        Raises:
            :class:`~ape.exceptions.NetworkError`: When the network already exists.

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
        """
        Create a deployment transaction in the given ecosystem.
        This may require connecting to other networks.

        Args:
            deployment_bytecode (HexBytes): The bytecode to deploy.
            abi (ConstructorABI): The constructor interface of the contract.
            *args: Constructor arguments.
            **kwargs: Transaction arguments.

        Returns:
            class:`~ape.api.transactions.TransactionAPI`
        """

    @abstractmethod
    def encode_transaction(
        self, address: AddressType, abi: MethodABI, *args, **kwargs
    ) -> "TransactionAPI":
        """
        Encode a transaction object from a contract function's abi and call arguments.
        Update the transaction arguments with the overrides in ``kwargs`` as well.

        Args:
            address (AddressType): The address of the contract.
            abi (MethodABI): The function to call on the contract.
            *args: Function arguments.
            **kwargs: Transaction arguments.

        Returns:
            class:`~ape.api.transactions.TransactionAPI`
        """

    @abstractmethod
    def decode_logs(self, logs: List[Dict], *events: EventABI) -> Iterator["ContractLog"]:
        """
        Decode any contract logs that match the given event ABI from the raw log data.

        Args:
            logs (List[Dict]): A list of raw log data from the chain.
            *events (EventABI): Event definitions to decode.

        Returns:
            Iterator[:class:`~ape.types.ContractLog`]
        """

    @raises_not_implemented
    def decode_primitive_value(  # type: ignore[empty-body]
        self, value: Any, output_type: Union[str, Tuple, List]
    ) -> Union[str, HexBytes, Tuple]:
        """
        Decode a primitive value-type given its ABI type as a ``str``
        and the value itself. This method is a hook for converting
        addresses, HexBytes, or other primitive data-types into
        friendlier Python equivalents.

        Args:
            value (Any): The value to decode.
            output_type (Union[str, Tuple, List]): The value type.

        Returns:
            Union[str, HexBytes, Tuple]
        """

    @abstractmethod
    def create_transaction(self, **kwargs) -> "TransactionAPI":
        """
        Create a transaction using key-value arguments.

        Args:
            **kwargs: Everything the transaction needs initialize.

        Returns:
            class:`~ape.api.transactions.TransactionAPI`
        """

    @abstractmethod
    def decode_calldata(self, abi: Union[ConstructorABI, MethodABI], calldata: bytes) -> Dict:
        """
        Decode method calldata.

        Args:
            abi (MethodABI): The method called.
            calldata (bytes): The raw calldata bytes.

        Returns:
            Dict: A mapping of input names to decoded values.
            If an input is anonymous, it should use the stringified
            index of the input as the key.
        """

    @abstractmethod
    def encode_calldata(self, abi: Union[ConstructorABI, MethodABI], *args: Any) -> HexBytes:
        """
        Encode method calldata.

        Args:
            abi (Union[ConstructorABI, MethodABI]): The ABI of the method called.
            *args (Any): The arguments given to the method.

        Returns:
            HexBytes: The encoded calldata of the arguments to the given method.
        """

    @abstractmethod
    def decode_returndata(self, abi: MethodABI, raw_data: bytes) -> Any:
        """
        Get the result of a contract call.

        Arg:
            abi (MethodABI): The method called.
            raw_data (bytes): Raw returned data.

        Returns:
            Any: All of the values returned from the contract function.
        """

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

    def get_proxy_info(self, address: AddressType) -> Optional[ProxyInfoAPI]:
        """
        Information about a proxy contract such as proxy type and implementation address.

        Args:
            address (str): The address of the contract.

        Returns:
            Optional[:class:`~ape.api.networks.ProxyInfoAPI`]: Returns ``None`` if the contract
            does not use any known proxy pattern.
        """
        return None

    def get_method_selector(self, abi: MethodABI) -> HexBytes:
        """
        Get a contract method selector, typically via hashing such as ``keccak``.
        Defaults to using ``keccak`` but can be overridden in different ecosystems.

        Override example::

            from ape.api import EcosystemAPI
            from hexbytes import HexBytes

            class MyEcosystem(EcosystemAPI):
                def get_method_selector(self, abi: MethodABI) -> HexBytes:
                    return HexBytes(abi.selector.encode())  # Simple bytes selector

        Args:
            abi (MethodABI): The ABI object to use when calculating the
              selector bytes.

        Returns:
            HexBytes: The hashed method selector value.
        """

        return HexBytes(keccak(text=abi.selector)[:4])

    def enrich_calltree(self, call: CallTreeNode, **kwargs) -> CallTreeNode:
        """
        Enhance the data in the call tree using information about the ecosystem.

        Args:
            call (:class:`~ape.types.trace.CallTreeNode`): The call tree node to enrich.
            kwargs: Additional kwargs to help with enrichment.

        Returns:
            :class:`~ape.types.trace.CallTreeNode`
        """
        return call


class ProviderContextManager(ManagerAccessMixin):
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

    connected_providers: Dict[str, "ProviderAPI"] = {}
    provider_stack: List[str] = []

    def __init__(self, provider: "ProviderAPI"):
        self._provider = provider

    @property
    def empty(self) -> bool:
        return not self.connected_providers or not self.provider_stack

    def __enter__(self, *args, **kwargs):
        return self.push_provider()

    def __exit__(self, *args, **kwargs):
        self.pop_provider()

    def push_provider(self):
        must_connect = not self._provider.is_connected
        if must_connect:
            self._provider.connect()

        provider_id = self.get_provider_id(self._provider)
        if provider_id is None:
            raise ProviderNotConnectedError()

        self.provider_stack.append(provider_id)
        if provider_id in self.connected_providers:
            # Using already connected instance
            if must_connect:
                # Disconnect if had to connect to check chain ID
                self._provider.disconnect()

            self._provider = self.connected_providers[provider_id]
        else:
            # Adding provider for the first time. Retain connection.
            self.connected_providers[provider_id] = self._provider

        self.network_manager.active_provider = self._provider
        return self._provider

    def pop_provider(self):
        if self.empty:
            return

        # Clear last provider
        exiting_provider_id = self.provider_stack.pop()
        if not self.provider_stack:
            self.network_manager.active_provider = None
            return

        # Reset the original active provider
        previous_provider_id = self.provider_stack[-1]
        if previous_provider_id == exiting_provider_id:
            # Active provider is not changing
            return

        previous_provider = self.connected_providers[previous_provider_id]
        if previous_provider:
            self.network_manager.active_provider = previous_provider

    def disconnect_all(self):
        if self.empty:
            return

        for provider in self.connected_providers.values():
            provider.disconnect()

        self.network_manager.active_provider = None
        self.connected_providers = {}

    @classmethod
    def get_provider_id(cls, provider: "ProviderAPI") -> Optional[str]:
        if not provider.is_connected:
            return None

        return (
            f"{provider.network.ecosystem.name}:"
            f"{provider.network.name}:{provider.name}-"
            f"{provider.chain_id}"
        )


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

    request_header: Dict
    """A shareable network HTTP header."""

    _default_provider: str = ""

    @classmethod
    def create_adhoc_network(cls) -> "NetworkAPI":
        ethereum_class = None
        for plugin_name, ecosystem_class in cls.plugin_manager.ecosystems:
            if plugin_name == "ethereum":
                ethereum_class = ecosystem_class
                break

        if ethereum_class is None:
            raise NetworkError("Core Ethereum plugin missing.")

        data_folder = mkdtemp()
        request_header = cls.config_manager.REQUEST_HEADER
        init_kwargs = {"data_folder": data_folder, "request_header": request_header}
        ethereum = ethereum_class(**init_kwargs)  # type: ignore
        return cls(
            name="adhoc",
            ecosystem=ethereum,
            data_folder=data_folder,
            request_header=request_header,
            _default_provider="geth",
        )

    def __repr__(self) -> str:
        try:
            chain_id = self.chain_id
        except ProviderNotConnectedError:
            # Only happens on local networks
            chain_id = None

        network_key = f"{self.ecosystem.name}:{self.name}"
        content = f"{network_key} chain_id={self.chain_id}" if chain_id is not None else network_key
        return f"<{content}>"

    @property
    def config(self) -> PluginConfig:
        """
        The configuration of the network. See :class:`~ape.managers.config.ConfigManager`
        for more information on plugin configurations.
        """

        return self.config_manager.get_config(self.ecosystem.name)

    @property
    def _network_config(self) -> Dict:
        return self.config.get(self.name, {})

    @cached_property
    def gas_limit(self) -> GasLimit:
        return self._network_config.get("gas_limit", "auto")

    @property
    def chain_id(self) -> int:
        """
        The ID of the blockchain.

        **NOTE**: Unless overridden, returns same as
        :py:attr:`ape.api.providers.ProviderAPI.chain_id`.
        """

        return self.provider.chain_id

    @property
    def network_id(self) -> int:
        """
        The ID of the network.

        **NOTE**: Unless overridden, returns same as
        :py:attr:`~ape.api.networks.NetworkAPI.chain_id`.
        """
        return self.chain_id

    @property
    def required_confirmations(self) -> int:
        """
        The default amount of confirmations recommended to wait
        before considering a transaction "confirmed". Confirmations
        refer to the number of blocks that have been added since the
        transaction's block.
        """
        return self._network_config.get("required_confirmations", 0)

    @property
    def block_time(self) -> int:
        """
        The approximate amount of time it takes for a new block to get mined to the chain.
        Configure in your ``ape-config.yaml`` file.

        Config example::

            ethereum:
              mainnet:
                block_time: 15
        """

        return self._network_config.get("block_time", 0)

    @property
    def transaction_acceptance_timeout(self) -> int:
        """
        The amount of time to wait for a transaction to be accepted on the network.
        Does not include waiting for block-confirmations. Defaults to two minutes.
        Local networks use smaller timeouts.
        """
        return self._network_config.get(
            "transaction_acceptance_timeout", DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT
        )

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
        provider_settings: Optional[Dict] = None,
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

        provider_name = provider_name or self.default_provider
        if not provider_name:
            from ape.managers.config import CONFIG_FILE_NAME

            raise NetworkError(
                f"No default provider for network '{self.name}'. "
                f"Set one in your {CONFIG_FILE_NAME}:\n"
                f"\n{self.ecosystem.name}:"
                f"\n  {self.name}:"
                "\n    default_provider: <DEFAULT_PROVIDER>"
            )

        provider_settings = provider_settings or {}

        if ":" in provider_name:
            # NOTE: Shortcut that allows `--network ecosystem:network:http://...` to work
            provider_settings["uri"] = provider_name
            provider_name = "geth"

        if provider_name in self.providers:
            provider = self.providers[provider_name](provider_settings=provider_settings)

            provider_id = ProviderContextManager.get_provider_id(provider)
            if not provider_id:
                # Provider not yet connected
                return provider

            if provider_id in ProviderContextManager.connected_providers:
                return ProviderContextManager.connected_providers[provider_id]

            return provider

        else:
            message = f"'{provider_name}' is not a valid provider for network '{self.name}'"
            raise NetworkError(message)

    def use_provider(
        self,
        provider_name: str,
        provider_settings: Optional[Dict] = None,
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
            :class:`~ape.api.networks.ProviderContextManager`
        """

        settings = provider_settings or {}
        return ProviderContextManager(
            provider=self.get_provider(provider_name=provider_name, provider_settings=settings),
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
            raise NetworkError(f"Provider '{provider_name}' not found in network '{self.name}'.")

    def use_default_provider(
        self, provider_settings: Optional[Dict] = None
    ) -> ProviderContextManager:
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
            settings = provider_settings or {}
            return self.use_provider(self.default_provider, provider_settings=settings)

        raise NetworkError(f"No providers for network '{self.name}'.")

    def publish_contract(self, address: AddressType):
        """
        A convenience method to publish a contract to the explorer.

        Raises:
            :class:`~ape.exceptions.NetworkError`: When there is no explorer for this network.

        Args:
            address (``AddressType``): The address of the contract.
        """
        if not self.explorer:
            raise NetworkError("Unable to publish contract - no explorer plugin installed.")

        logger.info(f"Publishing and verifying contract using '{self.explorer.name}'.")
        self.explorer.publish_contract(address)

    def verify_chain_id(self, chain_id: int):
        """
        Verify a chain ID for this network.

        Args:
            chain_id (int): The chain ID to verify.

        Raises:
            :class:`~ape.exceptions.NetworkMismatchError`: When the network is
              not local or adhoc and has a different hardcoded chain ID than
              the given one.
        """
        if self.name not in ("adhoc", LOCAL_NETWORK_NAME) and self.chain_id != chain_id:
            raise NetworkMismatchError(chain_id, self)


def create_network_type(chain_id: int, network_id: int) -> Type[NetworkAPI]:
    """
    Easily create a :class:`~ape.api.networks.NetworkAPI` subclass.
    """

    class network_def(NetworkAPI):
        @property
        def chain_id(self) -> int:
            return chain_id

        @property
        def network_id(self) -> int:
            return network_id

    return network_def
