from typing import Dict, Iterator, Optional

import yaml
from dataclassy import dataclass
from pluggy import PluginManager  # type: ignore

from ape.api import EcosystemAPI, ProviderAPI, ProviderContextManager
from ape.exceptions import NetworkError
from ape.utils import cached_property

from .config import ConfigManager


@dataclass
class NetworkManager:
    """
    The set of all blockchain network ecosystems that Ape has registered through its plugin system.
    """

    config: ConfigManager
    plugin_manager: PluginManager
    active_provider: Optional[ProviderAPI] = None
    _default: Optional[str] = None

    @cached_property
    def ecosystems(self) -> Dict[str, EcosystemAPI]:
        return {
            plugin_name: ecosystem_class(
                name=plugin_name,
                network_manager=self,
                config_manager=self.config,
                plugin_manager=self.plugin_manager,
                data_folder=self.config.DATA_FOLDER / plugin_name,
                request_header=self.config.REQUEST_HEADER,
            )
            for plugin_name, ecosystem_class in self.plugin_manager.ecosystems
        }

    def __iter__(self) -> Iterator[str]:
        yield from self.ecosystems

    def __getitem__(self, ecosystem_name: str) -> EcosystemAPI:
        if ecosystem_name not in self.ecosystems:
            raise NetworkError(f"Unknown ecosystem '{ecosystem_name}'.")

        return self.ecosystems[ecosystem_name]

    def __getattr__(self, attr_name: str) -> EcosystemAPI:
        if attr_name not in self.ecosystems:
            raise AttributeError(f"{self.__class__.__name__} has no attribute '{attr_name}'.")

        return self.ecosystems[attr_name]

    @property
    def network_choices(self) -> Iterator[str]:
        """
        Produce the set of all possible network choices that could be provided
        for a "network selection" choice e.g. `--network [ECOSYSTEM:NETWORK:PROVIDER]`
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

    def parse_network_choice(
        self,
        network_choice: Optional[str] = None,
    ) -> ProviderContextManager:
        if network_choice is None:
            return self.default["development"].use_default_provider()

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
            return ecosystem["development"].use_default_provider()

        elif len(selections) == 2:
            # Only ecosystem and network were specified, not provider
            ecosystem_name, network_name = selections
            ecosystem = self.__getattr__(ecosystem_name or self.default_ecosystem.name)
            network = ecosystem[network_name or ecosystem.default_network]
            return network.use_default_provider()

        elif len(selections) == 3:
            # Everything is specified, use specified provider for ecosystem
            # and network
            ecosystem_name, network_name, provider_name = selections
            ecosystem = self.__getattr__(ecosystem_name or self.default_ecosystem.name)
            network = ecosystem[network_name or ecosystem.default_network]
            return network.use_provider(provider_name)

        else:
            # NOTE: Might be unreachable
            raise NetworkError("Invalid network selection.")

    @property
    def default_ecosystem(self) -> EcosystemAPI:
        if self._default:
            return self.ecosystems[self._default]

        # If explicit default is not set, use first registered ecosystem
        elif len(self.ecosystems) == 1:
            return self.ecosystems[list(self.__iter__())[0]]

        else:
            raise NetworkError("No ecosystems installed.")

    def set_default_ecosystem(self, ecosystem_name: str):
        if ecosystem_name in self.__iter__():
            self._default = ecosystem_name

        else:
            raise NetworkError("Not a registered ecosystem.")

    @property
    def network_data(self) -> Dict:
        """
        Creates a dictionary of data about networks in the ecosystem.

        Note: The keys are added in an opinionated order for nicely
        translating into yaml.
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
        return yaml.dump(self.network_data, sort_keys=False)
