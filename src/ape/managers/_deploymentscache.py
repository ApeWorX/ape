from contextlib import contextmanager
from pathlib import Path
from typing import Optional

from ape.managers.base import BaseManager
from ape.types.address import AddressType
from ape.utils.basemodel import BaseModel, DiskCacheableModel
from ape.utils.os import create_tempdir


class Deployment(BaseModel):
    """
    A single deployment of a contract in a network.
    """

    address: AddressType
    transaction_hash: Optional[str] = None

    def __getitem__(self, key: str):
        # Mainly exists for backwards compat.
        if key == "address":
            return self.address
        elif key == "transaction_hash":
            return self.transaction_hash

        raise KeyError(key)

    def get(self, key: str):
        # Mainly exists for backwards compat.
        try:
            return self[key]
        except KeyError:
            return None


class Deployments(DiskCacheableModel):
    """The deployments structured JSON."""

    ecosystems: dict[str, dict[str, dict[str, list[Deployment]]]] = {}


class DeploymentDiskCache(BaseManager):
    """
    Manage cached contract deployments.
    """

    def __init__(self):
        # NOTE: For some reason, deployments are all inside their ecosystem folders,
        #   but they still have the ecosystem key. Hence, the weird structure here.
        self._deployments: dict[str, Deployments] = {}
        self._base_path = None

    @property
    def _is_live_network(self) -> bool:
        return bool(self.network_manager.active_provider) and not self.provider.network.is_dev

    @property
    def cachefile(self) -> Path:
        base_path = self._base_path or self.provider.network.ecosystem.data_folder
        return base_path / "deployments_map.json"

    @property
    def _all_deployments(self) -> Deployments:
        if not self._is_live_network:
            # No file.
            if "local" not in self._deployments:
                self._deployments["local"] = Deployments()

            return self._deployments["local"]

        ecosystem_name = self.provider.network.ecosystem.name
        if ecosystem_name not in self._deployments:
            self._deployments[ecosystem_name] = Deployments.model_validate_file(self.cachefile)

        return self._deployments[ecosystem_name]

    def __getitem__(self, contract_name: str) -> list[Deployment]:
        return self.get_deployments(contract_name)

    def __setitem__(self, contract_name, deployments: list[Deployment]):
        self._set_deployments(contract_name, deployments)

    def __delitem__(self, contract_name: str):
        self.remove_deployments(contract_name)

    def get_deployments(
        self,
        contract_name: str,
        ecosystem_key: Optional[str] = None,
        network_key: Optional[str] = None,
    ) -> list[Deployment]:
        """
        Get the deployments of the given contract on the currently connected network.

        Args:
            contract_name (str): The name of the deployed contract.
            ecosystem_key (str | None): The ecosystem key. Defaults to
              the connected ecosystem's name.
            network_key (str | None): The network key. Defaults to the
              connected network's name.

        Returns:
            list[Deployment]
        """
        if not self.network_manager.connected and (not ecosystem_key or not network_key):
            # Allows it to work when not connected (testing?)
            return []

        ecosystem_name = ecosystem_key or self.provider.network.ecosystem.name
        network_name = network_key or self.provider.network.name.replace("-fork", "")
        return (
            self._all_deployments.ecosystems.get(ecosystem_name, {})
            .get(network_name, {})
            .get(contract_name, [])
        )

    def cache_deployment(
        self,
        address: AddressType,
        contract_name: str,
        transaction_hash: Optional[str] = None,
        ecosystem_key: Optional[str] = None,
        network_key: Optional[str] = None,
    ):
        """
        Update the deployments cache with a new contract.

        Args:
            address (AddressType): The address of the contract.
            contract_name (str): The name of the contract type.
            transaction_hash (Optional[str]): Optionally, the transaction has
              associated with the deployment transaction.
            ecosystem_key (str | None): The ecosystem key. Defaults to
              the connected ecosystem's name.
            network_key (str | None): The network key. Defaults to the
              connected network's name.
        """
        deployments = [
            *self.get_deployments(contract_name),
            Deployment(address=address, transaction_hash=transaction_hash),
        ]
        self._set_deployments(
            contract_name,
            deployments,
            ecosystem_key=ecosystem_key,
            network_key=network_key,
        )

    @contextmanager
    def use_temporary_cache(self):
        base_path = self._base_path
        deployments = self._deployments
        with create_tempdir() as temp_path:
            self._base_path = temp_path
            self._deployments = {}
            yield

        self._base_path = base_path
        self._deployments = deployments

    def _set_deployments(
        self,
        contract_name: str,
        deployments: list[Deployment],
        ecosystem_key: Optional[str] = None,
        network_key: Optional[str] = None,
    ):
        ecosystem_name = ecosystem_key or self.provider.network.ecosystem.name
        network_name = network_key or self.provider.network.name.replace("-fork", "")
        self._all_deployments.ecosystems.setdefault(ecosystem_name, {})
        self._all_deployments.ecosystems[ecosystem_name].setdefault(network_name, {})
        self._all_deployments.ecosystems[ecosystem_name][network_name][contract_name] = deployments

        # For live networks, cache the deployments to a file as well.
        if self._is_live_network:
            self._deployments[ecosystem_name].model_dump_file()

    def remove_deployments(self, contract_name: str):
        self._set_deployments(contract_name, [])

    def clear_local(self):
        self._deployments["local"] = Deployments()
