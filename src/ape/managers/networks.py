from typing import Dict, Iterator, Optional

import yaml
from dataclassy import dataclass
from pluggy import PluginManager  # type: ignore

from ape.api import EcosystemAPI, ProviderAPI, ProviderContextManager
from ape.exceptions import ConfigError, NetworkError

from .config import ConfigManager


@dataclass
class NetworkManager:
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

    config: ConfigManager
    plugin_manager: PluginManager
    _active_provider: Optional[ProviderAPI] = None
    _default: Optional[str] = None
    _ecosystems_by_project: Dict[str, Dict[str, EcosystemAPI]] = {}

    def __repr__(self):
        return f"<NetworkManager, active_provider={self.active_provider}>"

    @property
    def active_provider(self) -> Optional[ProviderAPI]:
        return self._active_provider

    @active_provider.setter
    def active_provider(self, new_value: ProviderAPI):
        from ape import chain

        new_value._chain = chain
        self._active_provider = new_value

    @property
    def ecosystems(self) -> Dict[str, EcosystemAPI]:
        """
        All the registered ecosystems in ``ape``, such as ``ethereum``.
        """
        project_name = self.config.PROJECT_FOLDER.stem
        if project_name in self._ecosystems_by_project:
            return self._ecosystems_by_project[project_name]

        ecosystem_dict = {}
        for plugin_name, ecosystem_class in self.plugin_manager.ecosystems:
            ecosystem = ecosystem_class(
                name=plugin_name,
                network_manager=self,
                config_manager=self.config,
                plugin_manager=self.plugin_manager,
                data_folder=self.config.DATA_FOLDER / plugin_name,
                request_header=self.config.REQUEST_HEADER,
            )
            ecosystem_config = self.config.get_config(plugin_name)
            if ecosystem_config:
                for network_name, network in ecosystem.networks.items():
                    network_config = ecosystem_config.get(network_name)
                    if not network_config:
                        continue

                    default_provider = network_config.get("default_provider")
                    if not default_provider:
                        continue

                    if default_provider in network.providers:
                        network.set_default_provider(default_provider)
                    else:
                        raise ConfigError(f"No provider named '{default_provider}'.")

            ecosystem_dict[plugin_name] = ecosystem

        self._ecosystems_by_project[project_name] = ecosystem_dict
        return ecosystem_dict

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
            raise NetworkError(f"Unknown ecosystem '{ecosystem_name}'.")

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
            raise AttributeError(f"{self.__class__.__name__} has no attribute '{attr_name}'.")

        return self.ecosystems[attr_name]

    @property
    def network_choices(self) -> Iterator[str]:
        """
        The set of all possible network choices available as a "network selection"
        e.g. ``--network [ECOSYSTEM:NETWORK:PROVIDER]``.

        Each value is in the form ``ecosystem:network:provider`` and shortened options also
        appear in the list. For example, ``::geth`` would default to ``:ethereum:development:geth``
        and both will be in the returned list. The values come from each
        :class:`~ape.api.providers.ProviderAPI` that is installed.

        Use the CLI command ``ape networks list`` to list all the possible network
        combinations.

        Returns:
            Iterator[str]: An iterator over all the network-choice possibilities.
        """
        for ecosystem_name, ecosystem in self.ecosystems.items():
            yield ecosystem_name
            for network_name, network in ecosystem.networks.items():
                if ecosystem_name == self.default_ecosystem.name:
                    yield f":{network_name}"

                yield f"{ecosystem_name}:{network_name}"

                for provider in network.providers:
                    if (
                        ecosystem_name == self.default_ecosystem.name
                        and network_name == ecosystem.default_network
                    ):
                        yield f"::{provider}"

                    elif ecosystem_name == self.default_ecosystem.name:
                        yield f":{network_name}:{provider}"

                    elif network_name == ecosystem.default_network:
                        yield f"{ecosystem_name}::{provider}"

                    yield f"{ecosystem_name}:{network_name}:{provider}"

    def get_provider_from_choice(
        self,
        network_choice: Optional[str] = None,
        provider_settings: Optional[Dict] = None,
    ) -> ProviderAPI:
        """
        Get a :class:`~ape.api.providers.ProviderAPI` from a network choice.
        A network choice is any value returned from
        :py:attr:`~ape.managers.networks.NetworkManager.network_choices`. Use the
        CLI command ``ape networks list`` to list all the possible network
        combinations.

        Raises:
            :class:`~ape.exceptions.NetworkError`: When the given network choice does not
              match any known network.

        Args:
            network_choice (str, optional): The network choice
              (see :py:attr:`~ape.managers.networks.NetworkManager.network_choices`).
              Defaults to the default ecosystem, network, and provider combination.
            provider_settings (dict, optional): Settings for the provider. Defaults to None.

        Returns:
            :class:`~ape.api.providers.ProviderAPI`
        """

        if network_choice is None:
            return self.default_ecosystem["development"].get_provider(
                provider_settings=provider_settings
            )

        selections = network_choice.split(":")

        # NOTE: Handle case when URI is passed e.g. "http://..."
        if len(selections) > 3:
            selections[2] = ":".join(selections[2:])

        if selections == network_choice or len(selections) == 1:
            # Either split didn't work (in which case it matches the start)
            # or there was nothing after the ``:`` (e.g. "ethereum:")
            ecosystem = self.__getattr__(selections[0] or self.default_ecosystem.name)
            # By default, the "development" network should be specified for
            # any ecosystem (this should not correspond to a production chain)
            return ecosystem["development"].get_provider(provider_settings=provider_settings)

        elif len(selections) == 2:
            # Only ecosystem and network were specified, not provider
            ecosystem_name, network_name = selections
            ecosystem = self.__getattr__(ecosystem_name or self.default_ecosystem.name)
            network = ecosystem[network_name or ecosystem.default_network]
            return network.get_provider(provider_settings=provider_settings)

        elif len(selections) == 3:
            # Everything is specified, use specified provider for ecosystem
            # and network
            ecosystem_name, network_name, provider_name = selections
            ecosystem = self.__getattr__(ecosystem_name or self.default_ecosystem.name)
            network = ecosystem[network_name or ecosystem.default_network]
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
    ) -> ProviderContextManager:
        """
        Parse a network choice into a context manager for managing a temporary
        connection to a provider. See
        :py:attr:`~ape.managers.networks.NetworkManager.network_choices` for all
        available choices (or use CLI command ``ape networks list``).

        Args:
            network_choice (str, optional): The network choice
              (see :py:attr:`~ape.managers.networks.NetworkManager.network_choices`).
              Defaults to the default ecosystem, network, and provider combination.
            provider_settings (dict, optional): Settings for the provider. Defaults to None.

        Returns:
            :class:`~api.api.networks.ProviderContextManager`
        """

        provider = self.get_provider_from_choice(
            network_choice, provider_settings=provider_settings
        )
        return ProviderContextManager(self, provider)

    @property
    def default_ecosystem(self) -> EcosystemAPI:
        """
        The default ecosystem. Call
        :meth:`~ape.managers.networks.NetworkManager.set_default_ecosystem` to
        change the default ecosystem. If a default is not set and there is
        only a single ecosystem installed, such as Ethereum, then get
        that ecosystem.
        """
        if self._default:
            return self.ecosystems[self._default]

        # If explicit default is not set, use first registered ecosystem
        elif len(self.ecosystems) == 1:
            return self.ecosystems[list(self.__iter__())[0]]

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

        if ecosystem_name in self.__iter__():
            self._default = ecosystem_name

        else:
            raise NetworkError(f"Ecosystem '{ecosystem_name}' is not a registered ecosystem.")

    @property
    def network_data(self) -> Dict:
        """
        Get a dictionary containing data about networks in the ecosystem.

        **NOTE**: The keys are added in an opinionated order for nicely
        translating into ``yaml``.

        Returns:
            dict
        """
        data: Dict = {"ecosystems": []}

        for ecosystem_name in self:
            ecosystem_data = self._get_ecosystem_data(ecosystem_name)
            data["ecosystems"].append(ecosystem_data)

        return data

    def _get_ecosystem_data(self, ecosystem_name) -> Dict:
        ecosystem = self[ecosystem_name]
        ecosystem_data = {"name": ecosystem_name}

        # Only add isDefault key when True
        if ecosystem_name == self.default_ecosystem.name:
            ecosystem_data["isDefault"] = True

        ecosystem_data["networks"] = []
        for network_name in getattr(self, ecosystem_name):
            network_data = ecosystem.get_network_data(network_name)
            ecosystem_data["networks"].append(network_data)

        return ecosystem_data

    @property
    def networks_yaml(self) -> str:
        """
        Get a ``yaml`` ``str`` representing all the networks
        in all the ecosystems.

        View the result via CLI command ``ape networks list --format yaml``.

        Returns:
            str
        """

        return yaml.dump(self.network_data, sort_keys=False)
