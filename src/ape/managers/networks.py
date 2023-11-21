import json
from functools import cached_property
from typing import Collection, Dict, Iterator, List, Optional, Set, Union

import yaml

from ape.api import EcosystemAPI, ProviderAPI, ProviderContextManager
from ape.api.networks import NetworkAPI
from ape.exceptions import ApeAttributeError, EcosystemNotFoundError, NetworkError
from ape.managers.base import BaseManager


class NetworkManager(BaseManager):
    """
    The set of all blockchain network ecosystems registered from the plugin system.
    Typically, you set the provider via the ``--network`` command line option.
    However, use this singleton for more granular access to networks.

    Usage example::

        from ape import networks

        # "networks" is the NetworkManager singleton
        with networks.ethereum.mainnet.use_provider("geth"):
           ...
    """

    _active_provider: Optional[ProviderAPI] = None
    _default: Optional[str] = None

    def __repr__(self):
        provider = self.active_provider
        class_name = self.__class__.__name__
        content = f"{class_name} active_provider={repr(provider)}" if provider else class_name
        return f"<{content}>"

    @property
    def active_provider(self) -> Optional[ProviderAPI]:
        """
        The currently connected provider if one exists. Otherwise, returns ``None``.
        """

        return self._active_provider

    @active_provider.setter
    def active_provider(self, new_value: ProviderAPI):
        self._active_provider = new_value

    @property
    def network(self) -> NetworkAPI:
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
    def ecosystem(self) -> EcosystemAPI:
        """
        The current ecosystem if connected to one.

        Raises:
            :class:`~ape.exceptions.ProviderNotConnectedError`: When there is
              no active provider at runtime.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`
        """
        return self.network.ecosystem

    def fork(
        self,
        provider_name: Optional[str] = None,
        provider_settings: Optional[Dict] = None,
    ) -> ProviderContextManager:
        """
        Fork the currently connected network.

        Args:
            provider_name (str, optional): The name of the provider to get. Defaults to ``None``.
              When ``None``, returns the default provider.
            provider_settings (dict, optional): Settings to apply to the provider. Defaults to
              ``None``.

        Returns:
            :class:`~ape.api.networks.ProviderContextManager`
        """
        forked_network = self.ecosystem.get_network(f"{self.network.name}-fork")
        provider_settings = provider_settings or {}

        if provider_name:
            return forked_network.use_provider(
                provider_name, provider_settings, disconnect_after=True
            )

        return forked_network.use_default_provider(provider_settings, disconnect_after=True)

    @property
    def ecosystem_names(self) -> Set[str]:
        """
        The set of all ecosystem names in ``ape``.
        """

        return {e[0] for e in self.plugin_manager.ecosystems}

    @property
    def network_names(self) -> Set[str]:
        """
        The set of all network names in ``ape``.
        """

        names = set()
        for ecosystem in self.ecosystems.values():
            for network in ecosystem.networks.keys():
                names.add(network)

        return names

    @property
    def provider_names(self) -> Set[str]:
        """
        The set of all provider names in ``ape``.
        """

        names = set()
        for ecosystem in self.ecosystems.values():
            for network in ecosystem.networks.values():
                for provider in network.providers.keys():
                    names.add(provider)

        return names

    @cached_property
    def ecosystems(self) -> Dict[str, EcosystemAPI]:
        """
        All the registered ecosystems in ``ape``, such as ``ethereum``.
        """

        def to_kwargs(name: str) -> Dict:
            return {
                "name": name,
                "data_folder": self.config_manager.DATA_FOLDER / name,
                "request_header": self.config_manager.REQUEST_HEADER,
            }

        ecosystems = self.plugin_manager.ecosystems
        return {n: cls(**to_kwargs(n)) for n, cls in ecosystems}  # type: ignore

    def create_adhoc_geth_provider(self, uri: str) -> ProviderAPI:
        """
        Create an ad-hoc connection to a URI using the GethProvider core plugin.
        **NOTE**: This provider will assume EVM-like behavior and this is generally not recommended.
        Use plugins when possible!

        Args:
            uri (str): The URI of the node.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`: The Geth provider
              implementation that comes with Ape.
        """

        geth_class = None
        for plugin_name, (_, _, provider_class) in self.plugin_manager.providers:
            if plugin_name == "geth":
                geth_class = provider_class
                break

        if geth_class is None:
            raise NetworkError("Core Geth plugin missing.")

        network = NetworkAPI.create_adhoc_network()
        return geth_class(
            network=network,
            provider_settings={"uri": uri},
            data_folder=network.data_folder,
            request_header=network.request_header,
        )

    def __iter__(self) -> Iterator[str]:
        """
        All the managed ecosystems in ``ape``, as an iterable.

        Returns:
            Iterator[:class:`~ape.api.networks.EcosystemAPI`]
        """
        yield from self.ecosystems

    def __getitem__(self, ecosystem_name: str) -> EcosystemAPI:
        """
        Get an ecosystem by name.

        Raises:
            :class:`~ape.exceptions.NetworkError`: When the given ecosystem name is
              unknown.

        Args:
            ecosystem_name (str): The name of the ecosystem to get.

        Returns:
            :class:`~ape.api.networks.EcosystemAPI`
        """
        if ecosystem_name not in self.ecosystems:
            raise IndexError(f"Unknown ecosystem '{ecosystem_name}'.")

        return self.ecosystems[ecosystem_name]

    def __getattr__(self, attr_name: str) -> EcosystemAPI:
        """
        Get an ecosystem via ``.`` access.

        Args:
            attr_name (str): The name of the ecosystem.

        Returns:
            :class:`~ape.api.networks.EcosystemAPI`

        Usage example::

            eth = networks.ethereum
        """

        if attr_name not in self.ecosystems:
            # First try alternating the hyphen and underscores.
            attr_name_fix = (
                attr_name.replace("_", "-") if "_" in attr_name else attr_name.replace("-", "_")
            )
            if attr_name_fix in self.ecosystems:
                return self.ecosystems[attr_name_fix]

            raise ApeAttributeError(f"{self.__class__.__name__} has no attribute '{attr_name}'.")

        return self.ecosystems[attr_name]

    def get_network_choices(
        self,
        ecosystem_filter: Optional[Union[List[str], str]] = None,
        network_filter: Optional[Union[List[str], str]] = None,
        provider_filter: Optional[Union[List[str], str]] = None,
    ) -> Iterator[str]:
        """
        The set of all possible network choices available as a "network selection"
        e.g. ``--network [ECOSYSTEM:NETWORK:PROVIDER]``.

        Each value is in the form ``ecosystem:network:provider`` and shortened options also
        appear in the list. For example, ``::geth`` would default to ``:ethereum:local:geth``
        and both will be in the returned list. The values come from each
        :class:`~ape.api.providers.ProviderAPI` that is installed.

        Use the CLI command ``ape networks list`` to list all the possible network
        combinations.

        Args:
            ecosystem_filter (Optional[Union[List[str], str]]): Get only the specified ecosystems.
              Defaults to getting all ecosystems.
            network_filter (Optional[Union[List[str], str]]): Get only the specified networks.
              Defaults to getting all networks in ecosystems.
            provider_filter (Optional[Union[List[str], str]]): Get only the specified providers.
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
                        and network_name == ecosystem.default_network
                    ):
                        yield f"::{provider_name}"

                    if ecosystem_name == self.default_ecosystem.name:
                        yield f":{network_name}:{provider_name}"

                    if network_name == ecosystem.default_network:
                        yield f"{ecosystem_name}::{provider_name}"

                    # Always include the full path as an option.
                    yield f"{ecosystem_name}:{network_name}:{provider_name}"

                # Providers were yielded if we reached this point.
                if ecosystem_name == self.default_ecosystem.name:
                    yield f":{network_name}"

                yield f"{ecosystem_name}:{network_name}"

            if ecosystem_has_providers:
                yield ecosystem_name

    def get_ecosystem(self, ecosystem_name: str) -> EcosystemAPI:
        """
        Get the ecosystem for the given name.

        Args:
            ecosystem_name (str): The name of the ecosystem to get.

        Raises:
            :class:`~ape.exceptions.NetworkError`: When the ecosystem is not found.

        Returns:
            :class:`~ape.api.networks.EcosystemAPI`
        """

        if ecosystem_name not in self.ecosystem_names:
            raise EcosystemNotFoundError(ecosystem_name, options=self.ecosystem_names)

        return self.ecosystems[ecosystem_name]

    def get_provider_from_choice(
        self,
        network_choice: Optional[str] = None,
        provider_settings: Optional[Dict] = None,
    ) -> ProviderAPI:
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
            return self.default_ecosystem[default_network].get_provider(
                provider_settings=provider_settings
            )

        elif network_choice.startswith("http://") or network_choice.startswith("https://"):
            return self.create_adhoc_geth_provider(network_choice)

        selections = network_choice.split(":")

        # NOTE: Handle case when URI is passed e.g. "http://..."
        if len(selections) > 3:
            selections[2] = ":".join(selections[2:])
            selections = selections[:3]

        if selections == network_choice or len(selections) == 1:
            # Either split didn't work (in which case it matches the start)
            # or there was nothing after the ``:`` (e.g. "ethereum:")
            ecosystem = self.get_ecosystem(selections[0] or self.default_ecosystem.name)
            # By default, the "local" network should be specified for
            # any ecosystem (this should not correspond to a production chain)
            default_network = ecosystem.default_network
            return ecosystem[default_network].get_provider(provider_settings=provider_settings)

        elif len(selections) == 2:
            # Only ecosystem and network were specified, not provider
            ecosystem_name, network_name = selections
            ecosystem = self.get_ecosystem(ecosystem_name or self.default_ecosystem.name)
            network = ecosystem.get_network(network_name or ecosystem.default_network)
            return network.get_provider(provider_settings=provider_settings)

        elif len(selections) == 3:
            # Everything is specified, use specified provider for ecosystem and network
            ecosystem_name, network_name, provider_name = selections
            ecosystem = self.get_ecosystem(ecosystem_name or self.default_ecosystem.name)
            network = ecosystem.get_network(network_name or ecosystem.default_network)
            return network.get_provider(
                provider_name=provider_name, provider_settings=provider_settings
            )

        else:
            # NOTE: Might be unreachable
            raise NetworkError("Invalid network selection.")

    def parse_network_choice(
        self,
        network_choice: Optional[str] = None,
        provider_settings: Optional[Dict] = None,
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
    def default_ecosystem(self) -> EcosystemAPI:
        """
        The default ecosystem. Call
        :meth:`~ape.managers.networks.NetworkManager.set_default_ecosystem` to
        change the default ecosystem. If a default is not set and there is
        only a single ecosystem installed, such as Ethereum, then get
        that ecosystem.
        """

        ecosystems = self.ecosystems  # NOTE: Also will load defaults

        if self._default:
            return ecosystems[self._default]

        elif self.config_manager.default_ecosystem:
            return ecosystems[self.config_manager.default_ecosystem]

        # If explicit default is not set, use first registered ecosystem
        elif len(ecosystems) > 0:
            return list(ecosystems.values())[0]

        else:
            raise NetworkError("No ecosystems installed.")

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
            self._default = ecosystem_name

        else:
            raise EcosystemNotFoundError(ecosystem_name, options=self.ecosystem_names)

    @property
    def network_data(self) -> Dict:
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
        data: Dict = {"ecosystems": []}

        for ecosystem_name in self:
            if ecosystem_filter and ecosystem_name not in ecosystem_filter:
                continue

            ecosystem_data = self._get_ecosystem_data(
                ecosystem_name, network_filter=network_filter, provider_filter=provider_filter
            )
            data["ecosystems"].append(ecosystem_data)

        return data

    def _get_ecosystem_data(
        self,
        ecosystem_name: str,
        network_filter: Optional[Collection[str]] = None,
        provider_filter: Optional[Collection[str]] = None,
    ) -> Dict:
        ecosystem = self[ecosystem_name]
        ecosystem_data: Dict = {"name": str(ecosystem_name)}

        # Only add isDefault key when True
        if ecosystem_name == self.default_ecosystem.name:
            ecosystem_data["isDefault"] = True

        ecosystem_data["networks"] = []

        for network_name in getattr(self, ecosystem_name).networks:
            if network_filter and network_name not in network_filter:
                continue

            network_data = ecosystem.get_network_data(network_name, provider_filter=provider_filter)
            ecosystem_data["networks"].append(network_data)

        return ecosystem_data

    @property
    # TODO: Remove in 0.7
    def networks_yaml(self) -> str:
        """
        Get a ``yaml`` ``str`` representing all the networks
        in all the ecosystems.
        **NOTE**: Deprecated.

        View the result via CLI command ``ape networks list --format yaml``.

        Returns:
            str
        """

        data = self.network_data
        if not isinstance(data, dict):
            raise TypeError(
                f"Unexpected network data type: {type(data)}. "
                f"Expecting dict. YAML dump will fail."
            )

        try:
            return yaml.dump(data, sort_keys=True)
        except ValueError as err:
            try:
                data_str = json.dumps(data)
            except Exception:
                data_str = str(data)

            raise NetworkError(
                f"Network data did not dump to YAML: {data_str}\nActual err: {err}"
            ) from err


def _validate_filter(arg: Optional[Union[List[str], str]], options: Set[str]):
    filters = arg or []

    if isinstance(filters, str):
        filters = [filters]

    for _filter in filters:
        if _filter not in options:
            raise NetworkError(f"Unknown option '{_filter}'.")

    return filters
