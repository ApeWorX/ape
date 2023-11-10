from functools import partial
from pathlib import Path
from tempfile import mkdtemp
from typing import (
    TYPE_CHECKING,
    Any,
    ClassVar,
    Collection,
    Dict,
    Iterator,
    List,
    Optional,
    Tuple,
    Type,
    Union,
)

from eth_account import Account as EthAccount
from eth_account._utils.legacy_transactions import (
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_utils import keccak, to_int
from ethpm_types import ContractType, HexBytes
from ethpm_types.abi import ABIType, ConstructorABI, EventABI, MethodABI

from ape._pydantic_compat import BaseModel
from ape.exceptions import (
    NetworkError,
    NetworkMismatchError,
    NetworkNotFoundError,
    ProviderNotConnectedError,
    ProviderNotFoundError,
    SignatureError,
)
from ape.logging import logger
from ape.types import AddressType, AutoGasLimit, CallTreeNode, ContractLog, GasLimit, RawAddress
from ape.utils import (
    DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT,
    BaseInterfaceModel,
    ExtraModelAttributes,
    ManagerAccessMixin,
    abstractmethod,
    cached_property,
    raises_not_implemented,
)

from .config import PluginConfig

if TYPE_CHECKING:
    from .explorers import ExplorerAPI
    from .providers import BlockAPI, ProviderAPI, UpstreamProvider
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

    fee_token_decimals: int = 18
    """The number of the decimals the fee token has."""

    _default_network: Optional[str] = None

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

    @raises_not_implemented
    def encode_contract_blueprint(  # type: ignore[empty-body]
        self, contract_type: ContractType, *args, **kwargs
    ) -> "TransactionAPI":
        """
        Encode a unique type of transaction that allows contracts to be created
        from other contracts, such as
        `EIP-5202 <https://eips.ethereum.org/EIPS/eip-5202>`__
        or Starknet's ``Declare`` transaction type.

        Args:
            contract_type (``ContractType``): The type of contract to create a blueprint for.
              This is the type of contract that will get created by factory contracts.
            *args: Calldata, if applicable.
            **kwargs: Transaction specifications, such as ``value``.

        Returns:
            :class:`~ape.ape.transactions.TransactionAPI`
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
            self.signature.v,
            to_int(self.signature.r),
            to_int(self.signature.s),
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

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        yield ExtraModelAttributes(
            name="networks",
            attributes=self.networks,
            include_getattr=True,
            include_getitem=True,
        )

    def add_network(self, network_name: str, network: "NetworkAPI"):
        """
        Attach a new network to an ecosystem (e.g. L2 networks like Optimism).

        Raises:
            :class:`~ape.exceptions.NetworkError`: When the network already exists.

        Args:
            network_name (str): The name of the network to add.
            network (:class:`~ape.api.networks.NetworkAPI`): The network to add.
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

        if network := self._default_network:
            # Was set programatically.
            return network

        elif network := self.config.get("default_network"):
            # Default found in config.
            return network

        elif LOCAL_NETWORK_NAME in self.networks:
            # Default to the LOCAL_NETWORK_NAME, at last resort.
            return LOCAL_NETWORK_NAME

        elif len(self.networks) >= 1:
            # Use the first network.
            return self.networks[0]

        # Very unlikely scenario.
        raise ValueError("No networks found.")

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
            raise NetworkNotFoundError(network_name, ecosystem=self.name, options=self.networks)

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

        name = network_name.replace("_", "-")
        if name in self.networks:
            return self.networks[name]

        raise NetworkNotFoundError(network_name, ecosystem=self.name, options=self.networks)

    def get_network_data(
        self, network_name: str, provider_filter: Optional[Collection[str]] = None
    ) -> Dict:
        """
        Get a dictionary of data about providers in the network.

        **NOTE**: The keys are added in an opinionated order for nicely
        translating into ``yaml``.

        Args:
            network_name (str): The name of the network to get provider data from.
            provider_filter (Optional[Collection[str]]): Optionally filter the providers
              by name.

        Returns:
            dict: A dictionary containing the providers in a network.
        """
        data: Dict[str, Any] = {"name": str(network_name)}

        # Only add isDefault key when True
        if network_name == self.default_network:
            data["isDefault"] = True

        data["providers"] = []
        network = self[network_name]

        if network.explorer:
            data["explorer"] = str(network.explorer.name)

        for provider_name in network.providers:
            if provider_filter and provider_name not in provider_filter:
                continue

            provider_data: Dict = {"name": str(provider_name)}

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
            from ethpm_types import HexBytes

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

    @raises_not_implemented
    def get_python_types(  # type: ignore[empty-body]
        self, abi_type: ABIType
    ) -> Union[Type, Tuple, List]:
        """
        Get the Python types for a given ABI type.

        Args:
            abi_type (str): The ABI type to get the Python types for.

        Returns:
            List[Type]: The Python types for the given ABI type.
        """


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

        # Or, using choice-strings:

        with networks.parse_network_choice("ethereum:local:test"):
            ...
    """

    connected_providers: Dict[str, "ProviderAPI"] = {}
    provider_stack: List[str] = []
    disconnect_map: Dict[str, bool] = {}

    # We store a provider object at the class level for use when disconnecting
    # due to an exception, when interactive mode is set. If we don't hold on
    # to a reference to this object, the provider is dropped and reconnecting results
    # in losing state when using a spawned local provider
    _recycled_provider: ClassVar[Optional["ProviderAPI"]] = None

    def __init__(
        self,
        provider: "ProviderAPI",
        disconnect_after: bool = False,
        disconnect_on_exit: bool = True,
    ):
        self._provider = provider
        self._disconnect_after = disconnect_after
        self._disconnect_on_exit = disconnect_on_exit
        self._skipped_disconnect = False

    @property
    def empty(self) -> bool:
        return not self.connected_providers or not self.provider_stack

    def __enter__(self, *args, **kwargs):
        # If we have a recycled provider available, this means our last exit
        # was due to an exception during interactive mode. We should resume that
        # same connection, but also clear the object so we don't do this again
        # in later provider contexts, which we would want to behave normally
        if self._recycled_provider is not None:
            # set inner var to the recycled provider for use in push_provider()
            self._provider = self._recycled_provider
            ProviderContextManager._recycled_provider = None
        return self.push_provider()

    def __exit__(self, exception, *args, **kwargs):
        if not self._disconnect_on_exit and exception is not None:
            # We want to skip disconnection when exiting due to an exception in interactive mode
            if provider := self.network_manager.active_provider:
                ProviderContextManager._recycled_provider = provider
        else:
            self.pop_provider()

    def push_provider(self):
        must_connect = not self._provider.is_connected
        if must_connect:
            self._provider.connect()

        connection_id = self._provider.connection_id
        if connection_id is None:
            raise ProviderNotConnectedError()

        self.provider_stack.append(connection_id)
        self.disconnect_map[connection_id] = self._disconnect_after
        if connection_id in self.connected_providers:
            # Using already connected instance
            if must_connect:
                # Disconnect if had to connect to check chain ID
                self._provider.disconnect()

            self._provider = self.connected_providers[connection_id]
        else:
            # Adding provider for the first time. Retain connection.
            self.connected_providers[connection_id] = self._provider

        self.network_manager.active_provider = self._provider
        return self._provider

    def pop_provider(self):
        if self.empty:
            return

        # Clear last provider
        current_id = self.provider_stack.pop()

        # Disconnect the provider in same cases.
        if self.disconnect_map[current_id]:
            if provider := self.network_manager.active_provider:
                provider.disconnect()

            del self.disconnect_map[current_id]
            if current_id in self.connected_providers:
                del self.connected_providers[current_id]

        if not self.provider_stack:
            self.network_manager.active_provider = None
            return

        # Reset the original active provider
        prior_id = self.provider_stack[-1]
        if prior_id == current_id:
            # Active provider is not changing
            return

        if previous_provider := self.connected_providers[prior_id]:
            self.network_manager.active_provider = previous_provider

    def disconnect_all(self):
        if self.empty:
            return

        for provider in self.connected_providers.values():
            provider.disconnect()

        self.network_manager.active_provider = None
        self.connected_providers = {}


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
            data_folder=Path(data_folder),
            request_header=request_header,
            _default_provider="geth",
        )

    def __repr__(self) -> str:
        try:
            chain_id = self.chain_id
        except ProviderNotConnectedError:
            # Only happens on local networks
            chain_id = None

        content = f"{self.choice} chain_id={self.chain_id}" if chain_id is not None else self.choice
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
        return self.config.get(self.name.replace("-", "_"), {})

    @cached_property
    def gas_limit(self) -> GasLimit:
        return self._network_config.get("gas_limit", "auto")

    @cached_property
    def auto_gas_multiplier(self) -> float:
        """
        The value to multiply estimated gas by for tx-insurance.
        """
        return self.gas_limit.multiplier if isinstance(self.gas_limit, AutoGasLimit) else 1.0

    @property
    def base_fee_multiplier(self) -> float:
        """
        A multiplier to apply to a transaction base fee.
        """
        return self._network_config.get("base_fee_multiplier", 1.0)

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

    @property
    def is_fork(self) -> bool:
        """
        True when using a forked network.
        """
        return self.name.endswith("-fork")

    @property
    def is_local(self) -> bool:
        """
        True when using the local network.
        """
        return self.name == LOCAL_NETWORK_NAME

    @property
    def is_dev(self) -> bool:
        """
        True when using a local network, including forks.
        """
        return self.is_local or self.is_fork

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
            if provider.connection_id in ProviderContextManager.connected_providers:
                # Likely multi-chain testing or utilizing multiple on-going connections.
                return ProviderContextManager.connected_providers[provider.connection_id]

            return provider

        else:
            raise ProviderNotFoundError(
                provider_name,
                network=self.name,
                ecosystem=self.ecosystem.name,
                options=self.providers,
            )

    def use_provider(
        self,
        provider_name: str,
        provider_settings: Optional[Dict] = None,
        disconnect_after: bool = False,
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
            disconnect_after (bool): Set to ``True`` to force a disconnect after ending
              the context. This defaults to ``False`` so you can re-connect to the
              same network, such as in a multi-chain testing scenario.
            provider_settings (dict, optional): Settings to apply to the provider.
              Defaults to ``None``.

        Returns:
            :class:`~ape.api.networks.ProviderContextManager`
        """

        settings = provider_settings or {}
        provider = self.get_provider(provider_name=provider_name, provider_settings=settings)
        return ProviderContextManager(provider=provider, disconnect_after=disconnect_after)

    @property
    def default_provider(self) -> Optional[str]:
        """
        The name of the default provider or ``None``.

        Returns:
            Optional[str]
        """

        if provider := self._default_provider:
            # Was set programatically.
            return provider

        elif provider_from_config := self._network_config.get("default_provider"):
            # The default is found in the Network's config class.
            return provider_from_config

        elif len(self.providers) > 0:
            # No default set anywhere - use the first installed.
            return list(self.providers)[0]

        # There are no providers at all for this network.
        return None

    @property
    def choice(self) -> str:
        return f"{self.ecosystem.name}:{self.name}"

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
            raise NetworkError(f"Provider '{provider_name}' not found in network '{self.choice}'.")

    def use_default_provider(
        self,
        provider_settings: Optional[Dict] = None,
        disconnect_after: bool = False,
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
            disconnect_after (bool): Set to ``True`` to force a disconnect after ending
              the context. This defaults to ``False`` so you can re-connect to the
              same network, such as in a multi-chain testing scenario.

        Returns:
            :class:`~ape.api.networks.ProviderContextManager`
        """
        if self.default_provider:
            settings = provider_settings or {}
            return self.use_provider(
                self.default_provider, provider_settings=settings, disconnect_after=disconnect_after
            )

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


class ForkedNetworkAPI(NetworkAPI):
    @property
    def upstream_network(self) -> NetworkAPI:
        """
        The network being forked.
        """
        network_name = self.name.replace("-fork", "")
        return self.ecosystem.get_network(network_name)

    @property
    def upstream_provider(self) -> "UpstreamProvider":
        """
        The provider used when requesting data before the local fork.
        Set this in your config under the network settings.
        When not set, will attempt to use the default provider, if one
        exists.
        """

        config_choice = self._network_config.get("upstream_provider")
        if provider_name := config_choice or self.upstream_network.default_provider:
            return self.upstream_network.get_provider(provider_name)

        raise NetworkError(f"Upstream network '{self.upstream_network}' has no providers.")

    @property
    def upstream_chain_id(self) -> int:
        """
        The chain Id of the upstream network.
        For example, when on ``mainnet-fork``, this should always
        return the chain ID for ``mainnet``. Some providers may use
        a different chain ID for forked networks while some do not.
        This property should ALWAYS be that of the forked network, regardless.
        """
        return self.upstream_network.chain_id

    def use_upstream_provider(self) -> ProviderContextManager:
        """
        Connect to the upstream provider.

        Returns:
            :class:`~ape.api.networks.ProviderContextManager`
        """
        return self.upstream_network.use_provider(self.upstream_provider.name)


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
