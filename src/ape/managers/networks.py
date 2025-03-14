import os
import signal
from collections.abc import Collection, Iterator
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional, Union

from evmchains import PUBLIC_CHAIN_META
from pydantic import ValidationError

from ape.api.networks import ProviderContextManager
from ape.exceptions import EcosystemNotFoundError, NetworkError, NetworkNotFoundError
from ape.managers.base import BaseManager
from ape.utils.basemodel import (
    BaseModel,
    DiskCacheableModel,
    ExtraAttributesMixin,
    ExtraModelAttributes,
    get_attribute_with_extras,
    only_raise_attribute_error,
)
from ape.utils.misc import _dict_overlay, log_instead_of_fail
from ape.utils.os import clean_path
from ape_ethereum.provider import EthereumNodeProvider

if TYPE_CHECKING:
    from ape.api.networks import EcosystemAPI, NetworkAPI
    from ape.api.providers import ProviderAPI, SubprocessProvider
    from ape.utils.rpc import RPCHeaders


class NodeProcessData(BaseModel):
    """
    Cached data for node subprocesses managed by Ape.
    """

    network_choice: str
    """
    The network triple ``ecosystem:network:node``.
    """

    ipc_path: Optional[Path] = None
    """
    The IPC path this node process communicates on.
    """

    http_uri: Optional[str] = None
    """
    The HTTP URI this node process exposes.
    """

    ws_uri: Optional[str] = None
    """
    The websockets URI this node process exposes.
    """

    @log_instead_of_fail(default="<NodeProcessData>")
    def __repr__(self) -> str:
        if ipc := self.ipc_path:
            return f"{self.network_choice} - {clean_path(ipc)}"

        elif uri := (self.http_uri or self.ws_uri):
            return f"{self.network_choice} - {uri}"

        return self.network_choice

    def matches_provider(self, provider: "SubprocessProvider") -> bool:
        if self.network_choice != f"{provider.network.choice}:{provider.name}":
            return False

        # Skip if any of the connection paths (IPC, HTTP, WS) differ
        for attr in ("ipc_path", "http_uri", "ws_uri"):
            if getattr(provider, attr, None) != getattr(self, attr, None):
                return False

        return True


class NodeProcessMap(DiskCacheableModel):
    """
    All managed running network subprocesses.
    """

    nodes: dict[int, NodeProcessData] = {}

    @property
    def path(self) -> Path:
        return self._path

    @property
    def process_ids(self) -> tuple[int, ...]:
        return tuple(self.nodes.keys())

    def __bool__(self) -> bool:
        """
        True if there is at least one managed node process.
        """
        return bool(self.nodes)

    def __contains__(self, pid_or_provider: Union[int, "SubprocessProvider"]) -> bool:
        if isinstance(pid_or_provider, int):
            return pid_or_provider in self.nodes

        for data in self.nodes.values():
            if data.matches_provider(pid_or_provider):
                return True

        return False

    def get(self, pid: Union[int, str]) -> Optional[NodeProcessData]:
        return self.nodes.get(int(pid))

    def lookup_processes(self, provider: "SubprocessProvider") -> dict[int, NodeProcessData]:
        return {pid: data for pid, data in self.nodes.items() if data.matches_provider(provider)}

    def cache_provider(self, provider: "SubprocessProvider"):
        # Don't use `provider.network_choice` here because we want to ensure the provider
        # name is used and not the URI for the third part of the choice.
        network_choice = f"{provider.network.choice}:{provider.name}"
        data: dict[str, Any] = {
            "network_choice": network_choice,
            "ipc_path": provider.ipc_path,
            "http_uri": provider.http_uri,
            "ws_uri": provider.ws_uri,
        }
        data = {k: v for k, v in data.items() if v is not None}

        if process := provider.process:
            obj = NodeProcessData.model_validate(data)

            # Ensure no duplicates (bad clean?)
            self._delete_all_matching(obj)

            self.nodes[process.pid] = obj
            self.model_dump_file()

        else:
            raise NetworkError("Unable to cache subprocess-provider information: not connected.")

    def _delete_all_matching(self, node: NodeProcessData):
        pids_to_remove = set()
        for pid, other_node in self.nodes.items():
            if other_node == node:
                # Exact match but different PID. Bad clean.
                pids_to_remove.add(pid)

        for pid in pids_to_remove:
            del self.nodes[pid]

    def remove_provider(self, provider: "SubprocessProvider"):
        pids_to_remove = {
            pid for pid, data in self.nodes.items() if data.matches_provider(provider)
        }
        self.nodes = {pid: node for pid, node in self.nodes.items() if pid not in pids_to_remove}
        self.model_dump_file()

    def remove_processes(self, *pids: int):
        self.nodes = {k: v for k, v in self.nodes.items() if k not in pids}
        self.model_dump_file()

    def clean(self):
        self._path.unlink(missing_ok=True)


class NetworkManager(BaseManager, ExtraAttributesMixin):
    """
    The set of all blockchain network ecosystems registered from the plugin system.
    Typically, you set the provider via the ``--network`` command line option.
    However, use this singleton for more granular access to networks.

    Usage example::

        from ape import networks

        # "networks" is the NetworkManager singleton
        with networks.ethereum.mainnet.use_provider("node"):
            ...
    """

    _active_provider: Optional["ProviderAPI"] = None
    _default_ecosystem_name: Optional[str] = None

    # For adhoc adding custom networks, or incorporating some defined
    # in other projects' configs.
    _custom_networks: list[dict] = []

    @log_instead_of_fail(default="<NetworkManager>")
    def __repr__(self) -> str:
        provider = self.active_provider
        class_name = NetworkManager.__name__
        content = f"{class_name} active_provider={provider!r}" if provider else class_name
        return f"<{content}>"

    @property
    def active_provider(self) -> Optional["ProviderAPI"]:
        """
        The currently connected provider if one exists. Otherwise, returns ``None``.
        """
        return self._active_provider

    @active_provider.setter
    def active_provider(self, new_value: "ProviderAPI"):
        self._active_provider = new_value

    @property
    def connected(self) -> bool:
        """
        ``True`` when there is an active provider.
        """
        return self.active_provider is not None

    @property
    def network(self) -> "NetworkAPI":
        """
        The current network if connected to one.

        Raises:
            :class:`~ape.exceptions.ProviderNotConnectedError`: When there is
              no active provider at runtime.

        Returns:
            :class:`~ape.api.networks.NetworkAPI`
        """
        return self.provider.network

    @property
    def ecosystem(self) -> "EcosystemAPI":
        """
        The current ecosystem if connected to one.

        Raises:
            :class:`~ape.exceptions.ProviderNotConnectedError`: When there is
              no active provider at runtime.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`
        """
        return self.network.ecosystem

    @cached_property
    def running_nodes(self) -> NodeProcessMap:
        """
        All running development nodes managed by Ape.
        """
        path = self.config_manager.DATA_FOLDER / "processes" / "nodes.json"
        try:
            return NodeProcessMap.model_validate_file(path)
        except ValidationError:
            path.unlink(missing_ok=True)
            return NodeProcessMap.model_validate_file(path)

    def get_running_node(self, pid: int) -> "SubprocessProvider":
        """
        Get a running subprocess provider for the given ``pid``.

        Args:
            pid (int): The process ID.

        Returns:
            class:`~ape.api.providers.SubprocessProvider`
        """
        if not (data := self.running_nodes.get(pid)):
            raise NetworkError(f"No running node for pid '{pid}'.")

        uri: Optional[Union[str, Path]] = None
        if ipc := data.ipc_path:
            if ipc.exists():
                uri = ipc

        else:
            uri = data.http_uri or data.ws_uri

        if uri is None:
            NetworkError(f"Cannot connect to node on PID '{pid}': Missing URI data.")

        # In this case, we want the more connectable network choice.
        network_parts = data.network_choice.split(":")
        network_choice = f"{':'.join(network_parts[:2])}:{uri}"

        provider_settings: dict = {
            network_parts[0]: {
                network_parts[1]: {
                    "ipc_path": data.ipc_path,
                    "http_uri": data.http_uri,
                    "ws_uri": data.ws_uri,
                    "uri": None,
                }
            }
        }
        provider = self.get_provider_from_choice(
            network_choice=network_choice, provider_settings=provider_settings or None
        )

        # If this is not a subprocess provider, it may be ok to proceed.
        # However, the rest of Ape will assume it is.
        return provider  # type: ignore[return-value]

    def kill_node_process(self, *process_ids: int) -> dict[int, NodeProcessData]:
        """
        Kill a node process managed by Ape.

        Args:
            *process_ids (int): The process ID to kill.

        Returns:
            dict[str, :class:`~ape.managers.networks.NodeProcessData`]: The process data
            of all terminated processes.
        """
        if not self.running_nodes:
            return {}

        pids_killed = {}
        for pid in process_ids:
            if not (data := self.running_nodes.nodes.get(pid)):
                continue

            try:
                provider = self.get_running_node(pid)
            except Exception:
                # Still try to kill the process (below).
                pass
            else:
                # Gracefully disconnect _before_ killing process.
                provider.disconnect()

            try:
                os.kill(pid, signal.SIGTERM)
            except Exception:
                pass
            else:
                pids_killed[pid] = data

        self.running_nodes.remove_processes(*process_ids)
        return pids_killed

    def get_request_headers(
        self, ecosystem_name: str, network_name: str, provider_name: str
    ) -> "RPCHeaders":
        """
        All request headers to be used when connecting to this network.
        """
        ecosystem = self.get_ecosystem(ecosystem_name)
        network = ecosystem.get_network(network_name)
        provider = network.get_provider(provider_name)
        headers = self.config_manager._get_request_headers()
        for obj in (ecosystem, network, provider):
            for key, value in obj._get_request_headers().items():
                headers[key] = value

        return headers

    def fork(
        self,
        provider_name: Optional[str] = None,
        provider_settings: Optional[dict] = None,
        block_number: Optional[int] = None,
    ) -> ProviderContextManager:
        """
        Fork the currently connected network.

        Args:
            provider_name (str, optional): The name of the provider to get. Defaults to ``None``.
              When ``None``, returns the default provider.
            provider_settings (dict, optional): Settings to apply to the provider. Defaults to
              ``None``.
            block_number (Optional[int]): Optionally specify the block number you wish to fork.
              Negative block numbers are relative to HEAD. Defaults to the configured fork
              block number or HEAD.

        Returns:
            :class:`~ape.api.networks.ProviderContextManager`
        """
        network_name = self.network.name
        is_fork_already = network_name.endswith("-fork")
        forked_network_name = network_name if is_fork_already else f"{network_name}-fork"
        try:
            forked_network = self.ecosystem.get_network(forked_network_name)
        except NetworkNotFoundError as err:
            raise NetworkError(f"Unable to fork network '{network_name}'.") from err

        provider_settings = provider_settings or {}
        if is_fork_already and "host" not in provider_settings:
            # Forking a fork- to ensure is using a different Port,
            # use the "auto-port" feature.
            provider_settings["host"] = "auto"

        fork_settings = {}
        if block_number is not None:
            # Negative block_number means relative to HEAD
            if block_number < 0:
                latest_block_number = self.provider.get_block("latest").number or 0
                block_number = latest_block_number + block_number
                if block_number < 0:
                    # If the block number is still negative, they have forked past genesis.
                    raise NetworkError("Unable to fork past genesis block.")

            # Ensure block_number is set in config for this network
            fork_settings["block_number"] = block_number

        if uri := self.provider.connection_str:
            fork_settings["upstream_provider"] = uri

        _dict_overlay(
            provider_settings,
            {"fork": {self.ecosystem.name: {self.network.name: fork_settings}}},
        )

        shared_kwargs: dict = {
            "provider_settings": provider_settings,
            "disconnect_after": True,
        }
        return (
            forked_network.use_provider(provider_name, **shared_kwargs)
            if provider_name
            else forked_network.use_default_provider(**shared_kwargs)
        )

    @property
    def ecosystem_names(self) -> set[str]:
        """
        The set of all ecosystem names in ``ape``.
        """
        return set(self.ecosystems)

    @property
    def network_names(self) -> set[str]:
        """
        The set of all network names in ``ape``.
        """

        return {n for e in self.ecosystems.values() for n in e.networks}

    @property
    def provider_names(self) -> set[str]:
        """
        The set of all provider names in ``ape``.
        """

        return set(
            provider
            for ecosystem in self.ecosystems.values()
            for network in ecosystem.networks.values()
            for provider in network.providers
        )

    @property
    def custom_networks(self) -> list[dict]:
        """
        Custom network data defined in various ape-config files
        or added adhoc to the network manager.
        """
        return [*self._custom_networks_from_config, *self._custom_networks]

    @cached_property
    def _custom_networks_from_config(self) -> list[dict]:
        return [
            n.model_dump(by_alias=True)
            for n in self.config_manager.get_config("networks").get("custom", [])
        ]

    @property
    def ecosystems(self) -> dict[str, "EcosystemAPI"]:
        """
        All the registered ecosystems in ``ape``, such as ``ethereum``.
        """
        return {
            **self._evmchains_ecosystems,
            **self._plugin_ecosystems,
            **self._custom_ecosystems,
        }

    @cached_property
    def _plugin_ecosystems(self) -> dict[str, "EcosystemAPI"]:
        # Load plugins (possibly for first time).
        plugins: list[tuple] = self.plugin_manager.ecosystems
        return {n: cls(name=n) for n, cls in plugins}

    @cached_property
    def _custom_ecosystems(self) -> dict[str, "EcosystemAPI"]:
        custom_networks: list = self.custom_networks
        plugin_ecosystems = self._plugin_ecosystems
        evm_chains = self._evmchains_ecosystems
        custom_ecosystems: dict[str, EcosystemAPI] = {}
        for custom_network in custom_networks:
            ecosystem_name = custom_network["ecosystem"]
            if (
                ecosystem_name in plugin_ecosystems
                or ecosystem_name in evm_chains
                or ecosystem_name in custom_ecosystems
            ):
                # Already included in a prior network.
                continue

            base_ecosystem_name = (
                custom_network.get("base_ecosystem_plugin") or self.default_ecosystem_name
            )

            if base_ecosystem_name not in plugin_ecosystems:
                name = custom_network.get("name", "?")
                if eco := custom_network.get("ecosystem"):
                    name = f"{eco}:{name}"

                msg = (
                    f"Custom network '{name}' specified unknown base-ecosystem class "
                    f"'{base_ecosystem_name}'. Are you missing plugin 'ape-{base_ecosystem_name}'?"
                )
                raise NetworkError(msg)

            existing_cls = plugin_ecosystems[base_ecosystem_name]
            ecosystem_cls = existing_cls.model_copy(
                update={"name": ecosystem_name},
                cache_clear=("_networks_from_plugins", "_networks_from_evmchains"),
            )
            custom_ecosystems[ecosystem_name] = ecosystem_cls

        return custom_ecosystems

    @cached_property
    def _evmchains_ecosystems(self) -> dict[str, "EcosystemAPI"]:
        ecosystems: dict[str, EcosystemAPI] = {}
        for name in PUBLIC_CHAIN_META:
            ecosystem_name = name.lower().replace(" ", "-")
            symbol = None
            for net in PUBLIC_CHAIN_META[ecosystem_name].values():
                if not (native_currency := net.get("nativeCurrency")):
                    continue

                if "symbol" not in native_currency:
                    continue

                symbol = native_currency["symbol"]
                break

            symbol = symbol or "ETH"

            # Is an EVM chain, can automatically make a class using evm-chains.
            evm_class = self._plugin_ecosystems["ethereum"].__class__
            ecosystems[name] = evm_class(name=ecosystem_name, fee_token_symbol=symbol)

        return ecosystems

    def create_custom_provider(
        self,
        connection_str: str,
        provider_cls: type["ProviderAPI"] = EthereumNodeProvider,
        provider_name: Optional[str] = None,
    ) -> "ProviderAPI":
        """
        Create a custom connection to a URI using the EthereumNodeProvider provider.
        **NOTE**: This provider will assume EVM-like behavior and this is generally not recommended.
        Use plugins when possible!

        Args:
            connection_str (str): The connection string of the node, such as its URI
              when using HTTP.
            provider_cls (type[:class:`~ape.api.providers.ProviderAPI`]): Defaults to
              :class:`~ape_ethereum.providers.EthereumNodeProvider`.
            provider_name (Optional[str]): The name of the provider. Defaults to best guess.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`: The Geth provider
              implementation that comes with Ape.
        """

        network = self.ethereum.custom_network

        if provider_name is None:
            if issubclass(provider_cls, EthereumNodeProvider):
                name = "node"

            elif cls_name := getattr(provider_cls, "name", None):
                name = cls_name

            elif cls_name := provider_cls.__name__:
                name = cls_name.lower()

            else:
                # Would be unusual for this to happen though.
                name = "provider"

        else:
            name = provider_name

        provider_settings: dict = {}
        if connection_str.startswith("https://") or connection_str.startswith("http://"):
            provider_settings["uri"] = connection_str
        elif connection_str.endswith(".ipc"):
            provider_settings["ipc_path"] = connection_str
        else:
            raise NetworkError(f"Scheme for '{connection_str}' not yet supported.")

        return (provider_cls or EthereumNodeProvider)(
            name=name,
            network=network,
            provider_settings=provider_settings,
            data_folder=self.ethereum.data_folder / name,
        )

    def __iter__(self) -> Iterator[str]:
        """
        All the managed ecosystems in ``ape``, as an iterable.

        Returns:
            Iterator[:class:`~ape.api.networks.EcosystemAPI`]
        """
        yield from self.ecosystems

    def __ape_extra_attributes__(self) -> Iterator[ExtraModelAttributes]:
        yield ExtraModelAttributes(
            name="ecosystems",
            attributes=lambda: self.ecosystems,
            include_getitem=True,
        )

    @only_raise_attribute_error
    def __getattr__(self, attr_name: str) -> "EcosystemAPI":
        """
        Get an ecosystem via ``.`` access.

        Args:
            attr_name (str): The name of the ecosystem.

        Returns:
            :class:`~ape.api.networks.EcosystemAPI`

        Usage example::

            eth = networks.ethereum
        """
        return get_attribute_with_extras(self, attr_name)

    def get_network_choices(
        self,
        ecosystem_filter: Optional[Union[list[str], str]] = None,
        network_filter: Optional[Union[list[str], str]] = None,
        provider_filter: Optional[Union[list[str], str]] = None,
    ) -> Iterator[str]:
        """
        The set of all possible network choices available as a "network selection"
        e.g. ``--network [ECOSYSTEM:NETWORK:PROVIDER]``.

        Each value is in the form ``ecosystem:network:provider`` and shortened options also
        appear in the list. For example, ``::node`` would default to ``:ethereum:local:node``
        and both will be in the returned list. The values come from each
        :class:`~ape.api.providers.ProviderAPI` that is installed.

        Use the CLI command ``ape networks list`` to list all the possible network
        combinations.

        Args:
            ecosystem_filter (Optional[Union[list[str], str]]): Get only the specified ecosystems.
              Defaults to getting all ecosystems.
            network_filter (Optional[Union[list[str], str]]): Get only the specified networks.
              Defaults to getting all networks in ecosystems.
            provider_filter (Optional[Union[list[str], str]]): Get only the specified providers.
              Defaults to getting all providers in networks.

        Returns:
            Iterator[str]: An iterator over all the network-choice possibilities.
        """

        ecosystem_filter = _validate_filter(ecosystem_filter, self.ecosystem_names)
        network_filter = _validate_filter(network_filter, self.network_names)
        provider_filter = _validate_filter(provider_filter, self.provider_names)

        ecosystem_items = self.ecosystems
        if ecosystem_filter:
            ecosystem_items = {n: e for n, e in ecosystem_items.items() if n in ecosystem_filter}

        for ecosystem_name, ecosystem in ecosystem_items.items():
            network_items = ecosystem.networks
            if network_filter:
                network_items = {n: net for n, net in network_items.items() if n in network_filter}

            if not network_items:
                continue

            ecosystem_has_providers = False
            for network_name, network in network_items.items():
                providers = network.providers
                if provider_filter:
                    providers = [n for n in providers if n in provider_filter]

                network_has_providers = len(providers) > 0
                if not ecosystem_has_providers:
                    # Only check if we still haven't found any
                    ecosystem_has_providers = network_has_providers

                if not network_has_providers:
                    continue

                for provider_name in providers:
                    if (
                        ecosystem_name == self.default_ecosystem.name
                        and network_name == ecosystem.default_network_name
                    ):
                        yield f"::{provider_name}"

                    if ecosystem_name == self.default_ecosystem.name:
                        yield f":{network_name}:{provider_name}"

                    if network_name == ecosystem.default_network_name:
                        yield f"{ecosystem_name}::{provider_name}"

                    # Always include the full path as an option.
                    yield f"{ecosystem_name}:{network_name}:{provider_name}"

                # Providers were yielded if we reached this point.
                if ecosystem_name == self.default_ecosystem.name:
                    yield f":{network_name}"

                yield f"{ecosystem_name}:{network_name}"

            if ecosystem_has_providers:
                yield ecosystem_name

    def get_ecosystem(self, ecosystem_name: str) -> "EcosystemAPI":
        """
        Get the ecosystem for the given name.

        Args:
            ecosystem_name (str): The name of the ecosystem to get.

        Raises:
            :class:`~ape.exceptions.NetworkError`: When the ecosystem is not found.

        Returns:
            :class:`~ape.api.networks.EcosystemAPI`
        """
        # NOTE: This method purposely avoids "just checking self.ecosystems"
        #   for performance reasons and exiting the search as early as possible.
        ecosystem_name = ecosystem_name.lower().replace(" ", "-")
        try:
            return self._plugin_ecosystems[ecosystem_name]
        except KeyError:
            pass

        # Check if custom.
        try:
            return self._custom_ecosystems[ecosystem_name]
        except KeyError:
            pass

        if ecosystem := self._get_ecosystem_from_evmchains(ecosystem_name):
            return ecosystem

        raise EcosystemNotFoundError(ecosystem_name, options=self.ecosystem_names)

    def _get_ecosystem_from_evmchains(self, ecosystem_name: str) -> Optional["EcosystemAPI"]:
        if ecosystem_name not in PUBLIC_CHAIN_META:
            return None

        symbol = None
        for net in PUBLIC_CHAIN_META[ecosystem_name].values():
            if not (native_currency := net.get("nativeCurrency")):
                continue

            if "symbol" not in native_currency:
                continue

            symbol = native_currency["symbol"]
            break

        symbol = symbol or "ETH"

        # Is an EVM chain, can automatically make a class using evm-chains.
        evm_class = self._plugin_ecosystems["ethereum"].__class__
        return evm_class(name=ecosystem_name, fee_token_symbol=symbol)

    def get_provider_from_choice(
        self,
        network_choice: Optional[str] = None,
        provider_settings: Optional[dict] = None,
    ) -> "ProviderAPI":
        """
        Get a :class:`~ape.api.providers.ProviderAPI` from a network choice.
        A network choice is any value returned from
        :meth:`~ape.managers.networks.NetworkManager.get_network_choices`. Use the
        CLI command ``ape networks list`` to list all the possible network
        combinations.

        Raises:
            :class:`~ape.exceptions.NetworkError`: When the given network choice does not
              match any known network.

        Args:
            network_choice (str, optional): The network choice
              (see :meth:`~ape.managers.networks.NetworkManager.get_network_choices`).
              Defaults to the default ecosystem, network, and provider combination.
            provider_settings (dict, optional): Settings for the provider. Defaults to None.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`
        """
        if network_choice is None:
            default_network = self.default_ecosystem.default_network
            return default_network.get_provider(provider_settings=provider_settings)

        elif network_choice.startswith("pid://"):
            # Was given a process ID (already running node on local machine).
            pid_str = network_choice[len("pid://") :]
            if not pid_str.isdigit():
                raise ValueError(f"Invalid PID: {pid_str}")

            return self.get_running_node(int(pid_str))

        elif _is_adhoc_url(network_choice):
            # Custom network w/o ecosystem & network spec.
            return self.create_custom_provider(network_choice)

        selections = network_choice.split(":")

        # NOTE: Handle case when URI is passed e.g. "http://..."
        if len(selections) > 3:
            provider_value = ":".join(selections[2:])
            selections[2] = provider_value
            selections = selections[:3]
            if _is_adhoc_url(provider_value):
                selections[1] = selections[1] or "custom"

        if selections == network_choice or len(selections) == 1:
            # Either split didn't work (in which case it matches the start)
            # or there was nothing after the ``:`` (e.g. "ethereum:")
            ecosystem = self.get_ecosystem(selections[0] or self.default_ecosystem.name)
            # By default, the "local" network should be specified for
            # any ecosystem (this should not correspond to a production chain)
            default_network = ecosystem.default_network
            return default_network.get_provider(provider_settings=provider_settings)

        elif len(selections) == 2:
            # Only ecosystem and network were specified, not provider
            ecosystem_name, network_name = selections
            ecosystem = self.get_ecosystem(ecosystem_name or self.default_ecosystem.name)
            network = ecosystem.get_network(network_name or ecosystem.default_network_name)
            return network.get_provider(provider_settings=provider_settings)

        elif len(selections) == 3:
            # Everything is specified, use specified provider for ecosystem and network
            ecosystem_name, network_name, provider_name = selections
            ecosystem = (
                self.get_ecosystem(ecosystem_name) if ecosystem_name else self.default_ecosystem
            )
            network = ecosystem.get_network(network_name or ecosystem.default_network_name)
            return network.get_provider(
                provider_name=provider_name, provider_settings=provider_settings
            )

        else:
            # NOTE: Might be unreachable
            raise NetworkError("Invalid network selection.")

    def parse_network_choice(
        self,
        network_choice: Optional[str] = None,
        provider_settings: Optional[dict] = None,
        disconnect_after: bool = False,
        disconnect_on_exit: bool = True,
    ) -> ProviderContextManager:
        """
        Parse a network choice into a context manager for managing a temporary
        connection to a provider. See
        :meth:`~ape.managers.networks.NetworkManager.get_network_choices` for all
        available choices (or use CLI command ``ape networks list``).

        Raises:
            :class:`~ape.exceptions.NetworkError`: When the given network choice does not
              match any known network.

        Args:
            network_choice (str, optional): The network choice
              (see :meth:`~ape.managers.networks.NetworkManager.get_network_choices`).
              Defaults to the default ecosystem, network, and provider combination.
            provider_settings (dict, optional): Settings for the provider. Defaults to None.
            disconnect_after (bool): Set to True to terminate the connection completely
              at the end of context. NOTE: May only work if the network was also started
              from this session.
            disconnect_on_exit (bool): Whether to disconnect on the exit of the python
              session. Defaults to ``True``.

        Returns:
            :class:`~api.api.networks.ProviderContextManager`
        """
        provider = self.get_provider_from_choice(
            network_choice=network_choice, provider_settings=provider_settings
        )
        return ProviderContextManager(
            provider=provider,
            disconnect_after=disconnect_after,
            disconnect_on_exit=disconnect_on_exit,
        )

    @property
    def default_ecosystem_name(self) -> str:
        if name := self._default_ecosystem_name:
            return name

        return self.local_project.config.default_ecosystem or "ethereum"

    @cached_property
    def default_ecosystem(self) -> "EcosystemAPI":
        """
        The default ecosystem. Call
        :meth:`~ape.managers.networks.NetworkManager.set_default_ecosystem` to
        change the default ecosystem. If a default is not set and there is
        only a single ecosystem installed, such as Ethereum, then get
        that ecosystem.
        """
        return self.get_ecosystem(self.default_ecosystem_name)

    def set_default_ecosystem(self, ecosystem_name: str):
        """
        Change the default ecosystem.

        Raises:
            :class:`~ape.exceptions.NetworkError`: When the given ecosystem name is unknown.

        Args:
            ecosystem_name (str): The name of the ecosystem to set
              as the default.
        """
        if ecosystem_name in self.ecosystem_names:
            self._default_ecosystem_name = ecosystem_name

        else:
            raise EcosystemNotFoundError(ecosystem_name, options=self.ecosystem_names)

    @property
    def network_data(self) -> dict:
        """
        Get a dictionary containing data about networks in the ecosystem.

        **NOTE**: The keys are added in an opinionated order for nicely
        translating into ``yaml``.

        Returns:
            dict
        """
        return self.get_network_data()

    def get_network_data(
        self,
        ecosystem_filter: Optional[Collection[str]] = None,
        network_filter: Optional[Collection[str]] = None,
        provider_filter: Optional[Collection[str]] = None,
    ):
        data: dict = {"ecosystems": []}

        for ecosystem_name in self:
            if ecosystem_filter and ecosystem_name not in ecosystem_filter:
                continue

            ecosystem_data = self._get_ecosystem_data(
                ecosystem_name,
                network_filter=network_filter,
                provider_filter=provider_filter,
            )
            data["ecosystems"].append(ecosystem_data)

        return data

    def _get_ecosystem_data(
        self,
        ecosystem_name: str,
        network_filter: Optional[Collection[str]] = None,
        provider_filter: Optional[Collection[str]] = None,
    ) -> dict:
        ecosystem = self[ecosystem_name]
        ecosystem_data: dict = {"name": str(ecosystem_name)}

        # Only add isDefault key when True
        if ecosystem_name == self.default_ecosystem.name:
            ecosystem_data["isDefault"] = True

        ecosystem_data["networks"] = []
        networks = getattr(self, ecosystem_name).networks

        for network_name in networks:
            if network_filter and network_name not in network_filter:
                continue

            network_data = ecosystem.get_network_data(network_name, provider_filter=provider_filter)
            ecosystem_data["networks"].append(network_data)

        return ecosystem_data

    def _invalidate_cache(self):
        # NOTE: Called when changing config programmatically.
        self.__dict__.pop("_custom_ecosystems", None)
        self.__dict__.pop("_custom_networks_from_config", None)
        self._custom_networks = []


def _validate_filter(arg: Optional[Union[list[str], str]], options: set[str]):
    filters = arg or []

    if isinstance(filters, str):
        filters = [filters]

    for _filter in filters:
        if _filter not in options:
            raise NetworkError(f"Unknown option '{_filter}'.")

    return filters


def _is_adhoc_url(value: str) -> bool:
    return (
        value.startswith("http://")
        or value.startswith("https://")
        or value.startswith("ws://")
        or value.startswith("wss://")
        or (value.endswith(".ipc") and ":" not in value)
    )
