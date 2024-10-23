import copy
from abc import abstractmethod
from collections.abc import Collection, Iterator, Sequence
from functools import cached_property, partial
from pathlib import Path
from typing import TYPE_CHECKING, Any, ClassVar, Optional, Union

from eth_account import Account as EthAccount
from eth_account._utils.signing import (
    encode_transaction,
    serializable_unsigned_transaction_from_dict,
)
from eth_pydantic_types import HexBytes
from eth_utils import keccak, to_int
from ethpm_types import ContractType
from ethpm_types.abi import ABIType, ConstructorABI, EventABI, MethodABI
from pydantic import model_validator

from ape.exceptions import (
    CustomError,
    NetworkError,
    NetworkMismatchError,
    NetworkNotFoundError,
    ProviderNotConnectedError,
    ProviderNotFoundError,
    SignatureError,
)
from ape.logging import logger
from ape.types.address import AddressType, RawAddress
from ape.types.events import ContractLog
from ape.types.gas import AutoGasLimit, GasLimit
from ape.utils.basemodel import (
    BaseInterfaceModel,
    BaseModel,
    ExtraAttributesMixin,
    ExtraModelAttributes,
    ManagerAccessMixin,
)
from ape.utils.misc import (
    DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT,
    LOCAL_NETWORK_NAME,
    log_instead_of_fail,
    raises_not_implemented,
)
from ape.utils.rpc import RPCHeaders

from .config import PluginConfig

if TYPE_CHECKING:
    from .explorers import ExplorerAPI
    from .providers import BlockAPI, ProviderAPI, UpstreamProvider
    from .trace import TraceAPI
    from .transactions import ReceiptAPI, TransactionAPI


class ProxyInfoAPI(BaseModel):
    """
    Information about a proxy contract.
    """

    target: AddressType
    """The address of the implementation contract."""


class EcosystemAPI(ExtraAttributesMixin, BaseInterfaceModel):
    """
    A set of related networks, such as Ethereum.
    """

    name: str
    """
    The name of the ecosystem. This should be set the same name as the plugin.
    """

    # TODO: In 0.9, make @property that returns value from config,
    #   and use REQUEST_HEADER as plugin-defined constants.
    request_header: dict = {}
    """A shareable HTTP header for network requests."""

    fee_token_symbol: str
    """The token symbol for the currency that pays for fees, such as ETH."""

    fee_token_decimals: int = 18
    """The number of the decimals the fee token has."""

    _default_network: Optional[str] = None
    """The default network of the ecosystem, such as ``local``."""

    @model_validator(mode="after")
    @classmethod
    def _validate_ecosystem(cls, model):
        headers = RPCHeaders(**model.request_header)
        headers["User-Agent"] = f"ape-{model.name}"
        model.request_header = dict(**headers)
        return model

    @log_instead_of_fail(default="<EcosystemAPI>")
    def __repr__(self) -> str:
        return f"<{self.name}>"

    @property
    def data_folder(self) -> Path:
        """
        The path to the ecosystem's data folder,
        e.g. ``$HOME/.ape/{self.name}`` unless overridden.
        """
        return self.config_manager.DATA_FOLDER / self.name

    @cached_property
    def custom_network(self) -> "NetworkAPI":
        """
        A :class:`~ape.api.networks.NetworkAPI` for custom networks where the
        network is either not known, unspecified, or does not have an Ape plugin.
        """

        ethereum_class = None
        for plugin_name, ecosystem_class in self.plugin_manager.ecosystems:
            if plugin_name == "ethereum":
                ethereum_class = ecosystem_class
                break

        if ethereum_class is None:
            raise NetworkError("Core Ethereum plugin missing.")

        request_header = self.config_manager.REQUEST_HEADER
        init_kwargs = {"name": "ethereum", "request_header": request_header}
        ethereum = ethereum_class(**init_kwargs)  # type: ignore
        return NetworkAPI(
            name="custom",
            ecosystem=ethereum,
            request_header=request_header,
            _default_provider="node",
            _is_custom=True,
        )

    @classmethod
    @abstractmethod
    def decode_address(cls, raw_address: RawAddress) -> AddressType:
        """
        Convert a raw address to the ecosystem's native address type.

        Args:
            raw_address (:class:`~ape.types.address.RawAddress`): The address to
              convert.

        Returns:
            :class:`~ape.types.address.AddressType`
        """

    @classmethod
    @abstractmethod
    def encode_address(cls, address: AddressType) -> RawAddress:
        """
        Convert the ecosystem's native address type to a raw integer or str address.

        Args:
            address (:class:`~ape.types.address.AddressType`): The address to convert.

        Returns:
            :class:`~ape.types.address.RawAddress`
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
            *args (Any): Calldata, if applicable.
            **kwargs (Any): Transaction specifications, such as ``value``.

        Returns:
            :class:`~ape.ape.transactions.TransactionAPI`
        """

    def serialize_transaction(self) -> bytes:
        """
        Serialize a transaction to bytes.

        Returns:
            bytes
        """
        if not self.signature:
            raise SignatureError("The transaction is not signed.")

        txn_data = self.model_dump(exclude={"sender"})
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
            data (Dict): A dictionary of Receipt properties.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`
        """

    @abstractmethod
    def decode_block(self, data: dict) -> "BlockAPI":
        """
        Decode data to a :class:`~ape.api.providers.BlockAPI`.

        Args:
            data (Dict): A dictionary of data to decode.

        Returns:
            :class:`~ape.api.providers.BlockAPI`
        """

    @property
    def config(self) -> PluginConfig:
        """
        The configuration of the ecosystem. See :class:`ape.managers.config.ConfigManager`
        for more information on plugin configurations.

        Returns:
            :class:`ape.api.config.PluginConfig`
        """
        return self.config_manager.get_config(self.name)

    @property
    def networks(self) -> dict[str, "NetworkAPI"]:
        """
        A dictionary of network names mapped to their API implementation.

        Returns:
            dict[str, :class:`~ape.api.networks.NetworkAPI`]
        """
        networks = {**self._networks_from_plugins}

        # Include configured custom networks.
        custom_networks: list[dict] = [
            n
            for n in self.network_manager.custom_networks
            if n.get("ecosystem", self.network_manager.default_ecosystem.name) == self.name
        ]

        # Ensure forks are added automatically for custom networks.
        forked_custom_networks = []
        for net in custom_networks:
            if net["name"].endswith("-fork"):
                # Already a fork.
                continue

            fork_network_name = f"{net['name']}-fork"
            if any(x["name"] == fork_network_name for x in custom_networks):
                # The forked version of this network is already known.
                continue

            # Create a forked network mirroring the custom network.
            forked_net = copy.deepcopy(net)
            forked_net["name"] = fork_network_name
            forked_custom_networks.append(forked_net)

        # NOTE: Forked custom networks are still custom networks.
        custom_networks.extend(forked_custom_networks)

        for custom_net in custom_networks:
            model_data = copy.deepcopy(custom_net)
            net_name = custom_net["name"]
            if net_name in networks:
                raise NetworkError(
                    f"More than one network named '{net_name}' in ecosystem '{self.name}'."
                )

            is_fork = net_name.endswith("-fork")
            model_data["ecosystem"] = self
            network_type = create_network_type(
                custom_net["chain_id"], custom_net["chain_id"], is_fork=is_fork
            )
            if "request_header" not in model_data:
                model_data["request_header"] = self.request_header

            network_api = network_type.model_validate(model_data)
            network_api._default_provider = custom_net.get("default_provider", "node")
            network_api._is_custom = True
            networks[net_name] = network_api

        return networks

    @cached_property
    def _networks_from_plugins(self) -> dict[str, "NetworkAPI"]:
        return {
            network_name: network_class(name=network_name, ecosystem=self)
            for _, (ecosystem_name, network_name, network_class) in self.plugin_manager.networks
            if ecosystem_name == self.name
        }

    def __post_init__(self):
        if len(self.networks) == 0:
            raise NetworkError("Must define at least one network in ecosystem")

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        yield ExtraModelAttributes(
            name="networks",
            attributes=lambda: self.networks,
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
    def default_network_name(self) -> str:
        """
        The name of the default network in this ecosystem.

        Returns:
            str
        """
        if network := self._default_network:
            # Was set programmatically.
            return network

        elif network := self.config.get("default_network"):
            # Default found in config. Ensure is an installed network.
            if network in self.networks:
                return network

        if LOCAL_NETWORK_NAME in self.networks:
            # Default to the LOCAL_NETWORK_NAME, at last resort.
            return LOCAL_NETWORK_NAME

        elif len(self.networks) >= 1:
            # Use the first network.
            key = next(iter(self.networks.keys()))
            return self.networks[key].name

        # Very unlikely scenario.
        raise NetworkError("No networks found.")

    @property
    def default_network(self) -> "NetworkAPI":
        return self.get_network(self.default_network_name)

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
            *args (Any): Constructor arguments.
            **kwargs (Any): Transaction arguments.

        Returns:
            class:`~ape.api.transactions.TransactionAPI`
        """

    @abstractmethod
    def encode_transaction(
        self, address: AddressType, abi: MethodABI, *args, **kwargs
    ) -> "TransactionAPI":
        """
        Encode a transaction object from a contract function's ABI and call arguments.
        Additionally, update the transaction arguments with the overrides in ``kwargs``.

        Args:
            address (:class:`~ape.types.address.AddressType`): The address of the contract.
            abi (``MethodABI``): The function to call on the contract.
            *args (Any): Function arguments.
            **kwargs (Any): Transaction arguments.

        Returns:
            class:`~ape.api.transactions.TransactionAPI`
        """

    @abstractmethod
    def decode_logs(self, logs: Sequence[dict], *events: EventABI) -> Iterator[ContractLog]:
        """
        Decode any contract logs that match the given event ABI from the raw log data.

        Args:
            logs (Sequence[Dict]): A list of raw log data from the chain.
            *events (EventABI): Event definitions to decode.

        Returns:
            Iterator[:class:`~ape.types.ContractLog`]
        """

    @raises_not_implemented
    def decode_primitive_value(  # type: ignore[empty-body]
        self, value: Any, output_type: Union[str, tuple, list]
    ) -> Union[str, HexBytes, tuple]:
        """
        Decode a primitive value-type given its ABI type as a ``str``
        and the value itself. This method is a hook for converting
        addresses, HexBytes, or other primitive data-types into
        friendlier Python equivalents.

        Args:
            value (Any): The value to decode.
            output_type (Union[str, tuple, list]): The value type.

        Returns:
            Union[str, HexBytes, tuple]
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
    def decode_calldata(self, abi: Union[ConstructorABI, MethodABI], calldata: bytes) -> dict:
        """
        Decode method calldata.

        Args:
            abi (Union[ConstructorABI, MethodABI]): The method called.
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

        names = {network_name, network_name.replace("-", "_"), network_name.replace("_", "-")}
        networks = self.networks
        for name in names:
            if name in networks:
                return networks[name]

            elif name == "custom":
                # Is an adhoc-custom network NOT from config.
                return self.custom_network

        raise NetworkNotFoundError(network_name, ecosystem=self.name, options=networks)

    def get_network_data(
        self, network_name: str, provider_filter: Optional[Collection[str]] = None
    ) -> dict:
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
        data: dict[str, Any] = {"name": str(network_name)}

        # Only add isDefault key when True
        if network_name == self.default_network_name:
            data["isDefault"] = True

        data["providers"] = []
        network = self[network_name]

        if network.explorer:
            data["explorer"] = str(network.explorer.name)

        for provider_name in network.providers:
            if provider_filter and provider_name not in provider_filter:
                continue

            provider_data: dict = {"name": str(provider_name)}

            # Only add isDefault key when True
            if provider_name == network.default_provider_name:
                provider_data["isDefault"] = True

            data["providers"].append(provider_data)

        return data

    def get_proxy_info(self, address: AddressType) -> Optional[ProxyInfoAPI]:
        """
        Information about a proxy contract such as proxy type and implementation address.

        Args:
            address (:class:`~ape.types.address.AddressType`): The address of the contract.

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
            from eth_pydantic_types import HexBytes

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

    def enrich_trace(self, trace: "TraceAPI", **kwargs) -> "TraceAPI":
        """
        Enhance the data in the call tree using information about the ecosystem.

        Args:
            trace (:class:`~ape.api.trace.TraceAPI`): The trace to enrich.
            **kwargs: Additional kwargs to control enrichment, defined at the
              plugin level.

        Returns:
            :class:`~ape.api.trace.TraceAPI`
        """
        return trace

    @raises_not_implemented
    def get_python_types(  # type: ignore[empty-body]
        self, abi_type: ABIType
    ) -> Union[type, Sequence]:
        """
        Get the Python types for a given ABI type.

        Args:
            abi_type (``ABIType``): The ABI type to get the Python types for.

        Returns:
            Union[Type, Sequence]: The Python types for the given ABI type.
        """

    @raises_not_implemented
    def decode_custom_error(
        self,
        data: HexBytes,
        address: AddressType,
        **kwargs,
    ) -> Optional[CustomError]:
        """
        Decode a custom error class from an ABI defined in a contract.

        Args:
            data (HexBytes): The error data containing the selector
              and input data.
            address (AddressType): The address of the contract containing
              the error.
            **kwargs: Additional init kwargs for the custom error class.

        Returns:
            Optional[CustomError]: If it able to decode one, else ``None``.
        """

    def _get_request_headers(self) -> RPCHeaders:
        # Internal helper method called by NetworkManager
        headers = RPCHeaders(**self.request_header)
        # Have to do it this way to avoid "multiple-keys" error.
        configured_headers: dict = self.config.get("request_headers", {})
        for key, value in configured_headers.items():
            headers[key] = value

        return headers


class ProviderContextManager(ManagerAccessMixin):
    """
    A context manager for temporarily connecting to a network.
    When entering the context, calls the :meth:`ape.api.providers.ProviderAPI.connect` method.
    And conversely, when exiting, calls the :meth:`ape.api.providers.ProviderPAI.disconnect`
    method, unless in a multi-chain context, in which case it disconnects all providers at
    the very end of the Python session.

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

    connected_providers: dict[str, "ProviderAPI"] = {}
    provider_stack: list[str] = []
    disconnect_map: dict[str, bool] = {}

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
        """
        ``True`` when there are no providers in the context.
        """

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


def _set_provider(provider: "ProviderAPI") -> "ProviderAPI":
    connection_id = provider.connection_id
    if connection_id in ProviderContextManager.connected_providers:
        # Likely multi-chain testing or utilizing multiple on-going connections.
        provider = ProviderContextManager.connected_providers[connection_id]
        if not provider.is_connected:
            provider.connect()

    return provider


class NetworkAPI(BaseInterfaceModel):
    """
    A wrapper around a provider for a specific ecosystem.
    """

    name: str  # Name given when registered in ecosystem
    """The name of the network."""

    ecosystem: EcosystemAPI
    """The ecosystem of the network."""

    # TODO: In 0.9, make @property that returns value from config,
    #   and use REQUEST_HEADER as plugin-defined constants.
    request_header: dict = {}
    """A shareable network HTTP header."""

    # See ``.default_provider`` which is the proper field.
    _default_provider: str = ""

    _is_custom: bool = False

    def __repr__(self) -> str:
        try:
            chain_id = self.chain_id
        except ProviderNotConnectedError:
            # Only happens on local networks
            chain_id = None

        try:
            content = (
                f"{self.choice} chain_id={self.chain_id}" if chain_id is not None else self.choice
            )
            return f"<{content}>"
        except Exception:
            # Don't allow repr to fail.
            try:
                name = self.name
            except Exception:
                name = None

            return f"<{name}>" if name else f"{type(self)}"

    @property
    def data_folder(self) -> Path:
        """
        The path to the network's data folder,
        e.g. ``$HOME/.ape/{self.ecosystem_name}/{self.name}`` unless
        overridden.
        """
        return self.ecosystem.data_folder / self.name

    @property
    def ecosystem_config(self) -> PluginConfig:
        """
        The configuration of the network. See :class:`~ape.managers.config.ConfigManager`
        for more information on plugin configurations.
        """
        return self.ecosystem.config

    @property
    def config(self) -> PluginConfig:
        name_options = {self.name, self.name.replace("-", "_"), self.name.replace("_", "-")}
        cfg: Any
        for opt in name_options:
            if cfg := self.ecosystem_config.get(opt):
                if isinstance(cfg, dict):
                    return cfg
                elif isinstance(cfg, PluginConfig):
                    return cfg
                else:
                    raise TypeError(f"Network config must be a dictionary. Received '{type(cfg)}'.")

        return PluginConfig()

    @cached_property
    def gas_limit(self) -> GasLimit:
        return self.config.get("gas_limit", "auto")

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
        return self.config.get("base_fee_multiplier", 1.0)

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
        return self.config.get("required_confirmations", 0)

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

        return self.config.get("block_time", 0)

    @property
    def transaction_acceptance_timeout(self) -> int:
        """
        The amount of time to wait for a transaction to be accepted on the network.
        Does not include waiting for block-confirmations. Defaults to two minutes.
        Local networks use smaller timeouts.
        """
        return self.config.get(
            "transaction_acceptance_timeout", DEFAULT_TRANSACTION_ACCEPTANCE_TIMEOUT
        )

    @cached_property
    def explorer(self) -> Optional["ExplorerAPI"]:
        """
        The block-explorer for the given network.

        Returns:
            :class:`ape.api.explorers.ExplorerAPI`, optional
        """
        chain_id = None if self.network_manager.active_provider is None else self.provider.chain_id
        for plugin_name, plugin_tuple in self._plugin_explorers:
            ecosystem_name, network_name, explorer_class = plugin_tuple

            # Check for explicitly configured custom networks
            plugin_config = self.config_manager.get_config(plugin_name)
            has_explorer_config = (
                plugin_config
                and self.ecosystem.name in plugin_config
                and self.name in plugin_config[self.ecosystem.name]
            )

            # Return the first registered explorer (skipping any others)
            if self.ecosystem.name == ecosystem_name and (
                self.name == network_name or has_explorer_config
            ):
                return explorer_class(name=plugin_name, network=self)

            elif chain_id is not None and explorer_class.supports_chain(chain_id):
                # NOTE: Adhoc networks will likely reach here.
                return explorer_class(name=plugin_name, network=self)

        return None  # May not have an block explorer

    @property
    def _plugin_explorers(self) -> list[tuple]:
        # Abstracted for testing purposes.
        return self.plugin_manager.explorers

    @property
    def is_mainnet(self) -> bool:
        """
        True when the network is the mainnet network for the ecosystem.
        """
        cfg_is_mainnet: Optional[bool] = self.config.get("is_mainnet")
        if cfg_is_mainnet is not None:
            return cfg_is_mainnet

        return self.name == "mainnet"

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

    @property
    def is_adhoc(self) -> bool:
        """
        Is a custom network from CLI only, e.g. was not configured
        in any CLI value and is mostly an "unknown" network.
        """
        return self.name == "custom" and not self._is_custom

    @cached_property
    def providers(self):  # -> dict[str, Partial[ProviderAPI]]
        """
        The providers of the network, such as Infura, Alchemy, or Node.

        Returns:
            dict[str, partial[:class:`~ape.api.providers.ProviderAPI`]]
        """

        from ape.plugins._utils import clean_plugin_name

        providers = {}
        for _, plugin_tuple in self._get_plugin_providers():
            ecosystem_name, network_name, provider_class = plugin_tuple
            provider_name = clean_plugin_name(provider_class.__module__.split(".")[0])
            is_custom_with_config = self._is_custom and self.default_provider_name == provider_name
            # NOTE: Custom networks that are NOT from config must work with any provider.
            #    Also, ensure we are only adding forked providers for forked networks and
            #    non-forking providers for non-forked networks. For custom networks, it
            #    can be trickier (see last condition).
            # TODO: In 0.9, add a better way for class-level ForkedProviders to define
            #   themselves as "Fork" providers.
            if (
                self.is_adhoc
                or (self.ecosystem.name == ecosystem_name and self.name == network_name)
                or (
                    is_custom_with_config
                    and (
                        (self.is_fork and "Fork" in provider_class.__name__)
                        or (not self.is_fork and "Fork" not in provider_class.__name__)
                    )
                )
            ):
                # NOTE: Lazily load provider config
                providers[provider_name] = partial(
                    provider_class,
                    name=provider_name,
                    network=self,
                )

        return providers

    def _get_plugin_providers(self):
        # NOTE: Abstracted for testing purposes.
        return self.plugin_manager.providers

    def get_provider(
        self,
        provider_name: Optional[str] = None,
        provider_settings: Optional[dict] = None,
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
        provider_name = provider_name or self.default_provider_name
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
            provider_name = "node"

        elif provider_name.endswith(".ipc"):
            provider_settings["ipc_path"] = provider_name
            provider_name = "node"

        # If it can fork Ethereum (and we are asking for it) assume it can fork this one.
        # TODO: Refactor this approach to work for custom-forked non-EVM networks.
        common_forking_providers = self.network_manager.ethereum.mainnet_fork.providers
        if provider_name in self.providers:
            provider = self.providers[provider_name](provider_settings=provider_settings)
            return _set_provider(provider)

        elif self.is_fork and provider_name in common_forking_providers:
            provider = common_forking_providers[provider_name](
                provider_settings=provider_settings,
                network=self,
            )
            return _set_provider(provider)

        raise ProviderNotFoundError(
            provider_name,
            network=self.name,
            ecosystem=self.ecosystem.name,
            options=self.providers,
        )

    def use_provider(
        self,
        provider: Union[str, "ProviderAPI"],
        provider_settings: Optional[dict] = None,
        disconnect_after: bool = False,
        disconnect_on_exit: bool = True,
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
            provider (Union[str, :class:`~ape.api.providers.ProviderAPI`]): The provider
              instance or the name of the provider to use.
            provider_settings (dict, optional): Settings to apply to the provider.
              Defaults to ``None``.
            disconnect_after (bool): Set to ``True`` to force a disconnect after ending
              the context. This defaults to ``False`` so you can re-connect to the
              same network, such as in a multi-chain testing scenario.
            disconnect_on_exit (bool): Whether to disconnect on the exit of the python
              session. Defaults to ``True``.

        Returns:
            :class:`~ape.api.networks.ProviderContextManager`
        """

        settings = provider_settings or {}

        # NOTE: The main reason we allow a provider instance here is to avoid unnecessarily
        #   re-initializing the class.
        provider_obj = (
            self.get_provider(provider_name=provider, provider_settings=settings)
            if isinstance(provider, str)
            else provider
        )

        return ProviderContextManager(
            provider=provider_obj,
            disconnect_after=disconnect_after,
            disconnect_on_exit=disconnect_on_exit,
        )

    @property
    def default_provider_name(self) -> Optional[str]:
        """
        The name of the default provider or ``None``.

        Returns:
            Optional[str]
        """

        provider_from_config: str
        if provider := self._default_provider:
            # Was set programmatically.
            return provider

        elif provider_from_config := self.config.get("default_provider"):
            # The default is found in the Network's config class.
            return provider_from_config

        elif len(self.providers) > 0:
            # No default set anywhere - use the first installed.
            return list(self.providers)[0]

        # There are no providers at all for this network.
        return None

    @property
    def default_provider(self) -> Optional["ProviderAPI"]:
        if (name := self.default_provider_name) and name in self.providers:
            return self.get_provider(name)

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
        provider_settings: Optional[dict] = None,
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
                self.default_provider.name,
                provider_settings=settings,
                disconnect_after=disconnect_after,
            )

        raise NetworkError(f"No providers for network '{self.name}'.")

    def publish_contract(self, address: AddressType):
        """
        A convenience method to publish a contract to the explorer.

        Raises:
            :class:`~ape.exceptions.NetworkError`: When there is no explorer for this network.

        Args:
            address (:class:`~ape.types.address.AddressType`): The address of the contract.
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
        if self.name not in ("custom", LOCAL_NETWORK_NAME) and self.chain_id != chain_id:
            raise NetworkMismatchError(chain_id, self)

    def _get_request_headers(self) -> RPCHeaders:
        # Internal helper method called by NetworkManager
        headers = RPCHeaders(**self.request_header)
        # Have to do it this way to avoid multiple-keys error.
        configured_headers: dict = self.config.get("request_headers", {})
        for key, value in configured_headers.items():
            headers[key] = value

        return headers


class ForkedNetworkAPI(NetworkAPI):
    @property
    def upstream_network(self) -> NetworkAPI:
        """
        The network being forked.
        """
        network_name = self.name.replace("-fork", "").replace("_fork", "")
        return self.ecosystem.get_network(network_name)

    @property
    def upstream_provider(self) -> "UpstreamProvider":
        """
        The provider used when requesting data before the local fork.
        Set this in your config under the network settings.
        When not set, will attempt to use the default provider, if one
        exists.
        """

        config_choice: str = self.config.get("upstream_provider")
        if provider_name := config_choice or self.upstream_network.default_provider_name:
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
        return self.upstream_network.use_provider(self.upstream_provider)


def create_network_type(chain_id: int, network_id: int, is_fork: bool = False) -> type[NetworkAPI]:
    """
    Easily create a :class:`~ape.api.networks.NetworkAPI` subclass.
    """
    BaseNetwork = ForkedNetworkAPI if is_fork else NetworkAPI

    class network_def(BaseNetwork):  # type: ignore
        @property
        def chain_id(self) -> int:
            return chain_id

        @property
        def network_id(self) -> int:
            return network_id

    return network_def


# TODO: Can remove in 0.9 since `LOCAL_NETWORK_NAME` doesn't need to be here.
__all__ = [
    "create_network_type",
    "EcosystemAPI",
    "LOCAL_NETWORK_NAME",  # Have to leave for backwards compat.
    "ForkedNetworkAPI",
    "NetworkAPI",
    "ProviderContextManager",
    "ProxyInfoAPI",
]
