from typing import Dict, Iterator, Optional

from dataclassy import dataclass
from pluggy import PluginManager  # type: ignore

from ape.api import EcosystemAPI, ProviderAPI, ProviderContextManager
from ape.utils import cached_property

from .config import ConfigManager


@dataclass
class NetworkManager:
    """
    The set of all blockchain network ecosystems that Ape has registered through it's plugin system.

    You can access a network via the following:

    ```
    chain: ProviderAPI = networks.<ecosystem-name>.<chain-name>.use_provider(<provider-name>)
    ```

    e.g.

    ```
    eth_mainnet = networks.ethereum.mainnet.use_provider("http://localhost:8545")
    bsc_mainnet = networks.binance.mainnet.use_provider("infura")
    optimism = networks.ethereum.optimism  # use default provider
    zksync = networks.ethereum.zksync
    ```

    When there are multiple providers in use, you must specify which to work with:

    ```
    eth_contract = Contract.at(network=eth_mainnet)
    bsc_contract = account.deploy(Contract, network=bsc_mainnet)
    ```
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
                plugin_manager=self.plugin_manager,
                data_folder=self.config.DATA_FOLDER / plugin_name,
                request_header=self.config.REQUEST_HEADER,
            )
            for plugin_name, ecosystem_class in self.plugin_manager.ecosystems
        }

    def __iter__(self) -> Iterator[str]:
        for ecosystem_name in self.ecosystems:
            yield ecosystem_name

    def __getitem__(self, ecosystem_name: str) -> EcosystemAPI:
        if ecosystem_name not in self.ecosystems:
            raise Exception(f"Unknown ecosystem {ecosystem_name}")

        return self.ecosystems[ecosystem_name]

    def __getattr__(self, attr_name: str) -> EcosystemAPI:
        if attr_name not in self.ecosystems:
            raise AttributeError(f"{self.__class__.__name__} has no attribute '{attr_name}'")

        return self.ecosystems[attr_name]

    @property
    def network_choices(self) -> Iterator[str]:
        for ecosystem_name, ecosystem in self.ecosystems.items():
            yield ecosystem_name
            for network_name, network in ecosystem.networks.items():
                yield f"{ecosystem_name}:{network_name}"
                for provider in network.providers:
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
            # or there was nothing after the `:` (e.g. "ethereum:")
            ecosystem = self.__getattr__(selections[0])
            # By default, the "development" network should be specified for
            # any ecosystem (this should not correspond to a production chain)
            return ecosystem["development"].use_default_provider()

        elif len(selections) == 2:
            # Only ecosystem and network were specified, not provider
            ecosystem_name, network_name = selections
            ecosystem = self.__getattr__(ecosystem_name)
            network = ecosystem[network_name]
            return network.use_default_provider()

        elif len(selections) == 3:
            # Everything is specified, use specified provider for ecosystem
            # and network
            ecosystem_name, network_name, provider_name = selections
            ecosystem = self.__getattr__(ecosystem_name)
            network = ecosystem[network_name]
            return network.use_provider(provider_name)

        else:
            # NOTE: Might be unreachable
            raise Exception("Invalid selection")

    @property
    def default_ecosystem(self) -> EcosystemAPI:
        if self._default:
            return self.ecosystems[self._default]

        # If explicit default is not set, use first registered ecosystem
        elif len(self.ecosystems) == 1:
            return self.ecosystems[list(self.__iter__())[0]]

        else:
            raise Exception("No ecosystems installed")

    def set_default_ecosystem(self, ecosystem_name: str):
        if ecosystem_name in self.__iter__():
            self._default = ecosystem_name

        else:
            raise Exception("Not a registered ecosystem")
