import json
from collections.abc import Collection
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import cached_property
from pathlib import Path
from typing import TYPE_CHECKING, Generic, Optional, TypeVar, Union

from ethpm_types import ABI, ContractType
from pydantic import BaseModel

from ape.api.networks import ProxyInfoAPI
from ape.api.query import ContractCreation, ContractCreationQuery
from ape.contracts.base import ContractContainer, ContractInstance
from ape.exceptions import ApeException, ContractNotFoundError, ConversionError, CustomError
from ape.logging import logger
from ape.managers._deploymentscache import Deployment, DeploymentDiskCache
from ape.managers.base import BaseManager
from ape.types.address import AddressType
from ape.utils.misc import nonreentrant
from ape.utils.os import CacheDirectory

if TYPE_CHECKING:
    from eth_pydantic_types import HexBytes

    from ape.api.transactions import ReceiptAPI


_BASE_MODEL = TypeVar("_BASE_MODEL", bound=BaseModel)


class ApeDataCache(CacheDirectory, Generic[_BASE_MODEL]):
    """
    A wrapper around some cached models in the data directory,
    such as the cached contract types.
    """

    def __init__(
        self,
        base_data_folder: Path,
        ecosystem_key: str,
        network_key: str,
        key: str,
        model_type: type[_BASE_MODEL],
    ):
        data_folder = base_data_folder / ecosystem_key
        base_path = data_folder / network_key
        self._model_type = model_type
        self.memory: dict[str, _BASE_MODEL] = {}

        # Only write if we are not testing!
        self._write_to_disk = not network_key.endswith("-fork") and network_key != "local"
        # Read from disk if using forks or live networks.
        self._read_from_disk = network_key.endswith("-fork") or network_key != "local"

        super().__init__(base_path / key)

    def __getitem__(self, key: str) -> Optional[_BASE_MODEL]:  # type: ignore
        return self.get_type(key)

    def __setitem__(self, key: str, value: _BASE_MODEL):  # type: ignore
        self.memory[key] = value
        if self._write_to_disk:
            # Cache to disk.
            self.cache_data(key, value.model_dump(mode="json"))

    def __delitem__(self, key: str):
        self.memory.pop(key, None)
        if self._write_to_disk:
            # Delete the cache file.
            self.delete_data(key)

    def __contains__(self, key: str) -> bool:
        try:
            return bool(self[key])
        except KeyError:
            return False

    def get_type(self, key: str) -> Optional[_BASE_MODEL]:
        if model := self.memory.get(key):
            return model

        elif self._read_from_disk:
            if data := self.get_data(key):
                # Found on disk.
                model = self._model_type.model_validate(data)
                # Cache locally for next time.
                self.memory[key] = model
                return model

        return None


class ContractCache(BaseManager):
    """
    A collection of cached contracts. Contracts can be cached in two ways:

    1. An in-memory cache of locally deployed contracts
    2. A cache of contracts per network (only permanent networks are stored this way)

    When retrieving a contract, if a :class:`~ape.api.explorers.ExplorerAPI` is used,
    it will be cached to disk for faster look-up next time.
    """

    # ecosystem_name -> network_name -> cache_name -> cache
    _caches: dict[str, dict[str, dict[str, ApeDataCache]]] = {}

    # chain_id -> address -> custom_err
    # Cached to prevent calling `new_class` multiple times with conflicts.
    _custom_error_types: dict[int, dict[AddressType, set[type[CustomError]]]] = {}

    @property
    def contract_types(self) -> ApeDataCache[ContractType]:
        return self._get_data_cache("contract_types", ContractType)

    @property
    def proxy_infos(self) -> ApeDataCache[ProxyInfoAPI]:
        return self._get_data_cache("proxy_info", ProxyInfoAPI)

    @property
    def blueprints(self) -> ApeDataCache[ContractType]:
        return self._get_data_cache("blueprints", ContractType)

    @property
    def contract_creations(self) -> ApeDataCache[ContractCreation]:
        return self._get_data_cache("contract_creation", ContractCreation)

    def _get_data_cache(
        self,
        key: str,
        model_type: type,
        ecosystem_key: Optional[str] = None,
        network_key: Optional[str] = None,
    ):
        ecosystem_name = ecosystem_key or self.provider.network.ecosystem.name
        network_name = network_key or self.provider.network.name.replace("-fork", "")
        self._caches.setdefault(ecosystem_name, {})
        self._caches[ecosystem_name].setdefault(network_name, {})

        if cache := self._caches[ecosystem_name][network_name].get(key):
            return cache

        self._caches[ecosystem_name][network_name][key] = ApeDataCache(
            self.config_manager.DATA_FOLDER, ecosystem_name, network_name, key, model_type
        )
        return self._caches[ecosystem_name][network_name][key]

    @cached_property
    def deployments(self) -> DeploymentDiskCache:
        """A manager for contract deployments across networks."""
        return DeploymentDiskCache()

    def __setitem__(
        self, address: AddressType, item: Union[ContractType, ProxyInfoAPI, ContractCreation]
    ):
        """
        Cache the given contract type. Contracts are cached in memory per session.
        In live networks, contracts also get cached to disk at
        ``.ape/{ecosystem_name}/{network_name}/contract_types/{address}.json``
        for faster look-up next time.

        Args:
            address (AddressType): The on-chain address of the contract.
            item (ContractType | ProxyInfoAPI | ContractCreation): The contract's type, proxy info,
              or creation metadata.
        """
        # Note: Can't cache blueprints this way.
        address = self.provider.network.ecosystem.decode_address(int(address, 16))
        if isinstance(item, ContractType):
            self.cache_contract_type(address, item)
        elif isinstance(item, ProxyInfoAPI):
            self.cache_proxy_info(address, item)
        elif isinstance(item, ContractCreation):
            self.cache_contract_creation(address, item)
        elif contract_type := getattr(item, "contract_type", None):
            self.cache_contract_type(address, contract_type)
        else:
            raise TypeError(item)

    def cache_contract_type(
        self,
        address: AddressType,
        contract_type: ContractType,
        ecosystem_key: Optional[str] = None,
        network_key: Optional[str] = None,
    ):
        """
        Cache a contract type at the given address for the given network.
        If not connected, you must provider both ``ecosystem_key:`` and
        ``network_key::``.

        Args:
            address (AddressType): The address key.
            contract_type (ContractType): The contract type to cache.
            ecosystem_key (str | None): The ecosystem key. Defaults to
              the connected ecosystem's name.
            network_key (str | None): The network key. Defaults to the
              connected network's name.
        """
        # Get the cache in a way that doesn't require an active connection.
        cache = self._get_data_cache(
            "contract_types", ContractType, ecosystem_key=ecosystem_key, network_key=network_key
        )
        cache[address] = contract_type

        # NOTE: The txn_hash is not included when caching this way.
        if name := contract_type.name:
            self.deployments.cache_deployment(
                address, name, ecosystem_key=ecosystem_key, network_key=network_key
            )

    def cache_contract_creation(
        self,
        address: AddressType,
        contract_creation: ContractCreation,
        ecosystem_key: Optional[str] = None,
        network_key: Optional[str] = None,
    ):
        """
        Cache a contract creation object.

        Args:
            address (AddressType): The address of the contract.
            contract_creation (ContractCreation): The object to cache.
            ecosystem_key (str | None): The ecosystem key. Defaults to
              the connected ecosystem's name.
            network_key (str | None): The network key. Defaults to the
              connected network's name.
        """
        # Get the cache in a way that doesn't require an active connection.
        cache = self._get_data_cache(
            "contract_creation",
            ContractCreation,
            ecosystem_key=ecosystem_key,
            network_key=network_key,
        )
        cache[address] = contract_creation

    def __delitem__(self, address: AddressType):
        """
        Delete a cached contract.
        If using a live network, it will also delete the file-cache for the contract.

        Args:
            address (AddressType): The address to remove from the cache.
        """
        del self.contract_types[address]
        self._delete_proxy(address)
        del self.contract_creations[address]

    @contextmanager
    def use_temporary_caches(self):
        """
        Create temporary context where there are no cached items.
        Useful for testing.
        """
        caches = self._caches
        self._caches = {}
        with self.deployments.use_temporary_cache():
            yield

        self._caches = caches

    def _delete_proxy(self, address: AddressType):
        if info := self.proxy_infos[address]:
            target = info.target
            del self.proxy_infos[target]
            del self.contract_types[target]

    def __contains__(self, address: AddressType) -> bool:
        return self.get(address) is not None

    def cache_deployment(self, contract_instance: ContractInstance):
        """
        Cache the given contract instance's type and deployment information.

        Args:
            contract_instance (:class:`~ape.contracts.base.ContractInstance`): The contract
              to cache.
        """
        address = contract_instance.address
        contract_type = contract_instance.contract_type  # may be a proxy

        # Cache contract type in memory before proxy check,
        # in case it is needed somewhere. It may get overridden.
        self.contract_types.memory[address] = contract_type

        if proxy_info := self.provider.network.ecosystem.get_proxy_info(address):
            # The user is caching a deployment of a proxy with the target already set.
            self.cache_proxy_info(address, proxy_info)
            if implementation_contract := self.get(proxy_info.target):
                updated_proxy_contract = _get_combined_contract_type(
                    contract_type, proxy_info, implementation_contract
                )
                self.contract_types[address] = updated_proxy_contract

                # Use this contract type in the user's contract instance.
                contract_instance.contract_type = updated_proxy_contract

            else:
                # No implementation yet. Just cache proxy.
                self.contract_types[address] = contract_type

        else:
            # Regular contract. Cache normally.
            self.contract_types[address] = contract_type

        # Cache the deployment now.
        txn_hash = contract_instance.txn_hash
        if contract_name := contract_type.name:
            self.deployments.cache_deployment(address, contract_name, transaction_hash=txn_hash)

        return contract_type

    def cache_proxy_info(self, address: AddressType, proxy_info: ProxyInfoAPI):
        """
        Cache proxy info for a particular address, useful for plugins adding already
        deployed proxies. When you deploy a proxy locally, it will also call this method.

        Args:
            address (AddressType): The address of the proxy contract.
            proxy_info (:class:`~ape.api.networks.ProxyInfo`): The proxy info class
              to cache.
        """
        self.proxy_infos[address] = proxy_info

    def cache_blueprint(self, blueprint_id: str, contract_type: ContractType):
        """
        Cache a contract blueprint.

        Args:
            blueprint_id (``str``): The ID of the blueprint. For example, in EIP-5202,
              it would be the address of the deployed blueprint. For Starknet, it would
              be the class identifier.
            contract_type (``ContractType``): The contract type associated with the blueprint.
        """
        self.blueprints[blueprint_id] = contract_type

    def get_proxy_info(self, address: AddressType) -> Optional[ProxyInfoAPI]:
        """
        Get proxy information about a contract using its address,
        either from a local cache, a disk cache, or the provider.

        Args:
            address (AddressType): The address of the proxy contract.

        Returns:
            Optional[:class:`~ape.api.networks.ProxyInfoAPI`]
        """
        return self.proxy_infos[address]

    def get_creation_metadata(self, address: AddressType) -> Optional[ContractCreation]:
        """
        Get contract creation metadata containing txn_hash, deployer, factory, block.

        Args:
            address (AddressType): The address of the contract.

        Returns:
            Optional[:class:`~ape.api.query.ContractCreation`]
        """
        if creation := self.contract_creations[address]:
            return creation

        # Query and cache.
        query = ContractCreationQuery(columns=["*"], contract=address)
        get_creation = self.query_manager.query(query)

        try:
            if not (creation := next(get_creation, None)):  # type: ignore[arg-type]
                return None

        except ApeException:
            return None

        self.contract_creations[address] = creation
        return creation

    def get_blueprint(self, blueprint_id: str) -> Optional[ContractType]:
        """
        Get a cached blueprint contract type.

        Args:
            blueprint_id (``str``): The unique identifier used when caching
              the blueprint.

        Returns:
            ``ContractType``
        """
        return self.blueprints[blueprint_id]

    def _get_errors(
        self, address: AddressType, chain_id: Optional[int] = None
    ) -> set[type[CustomError]]:
        if chain_id is None and self.network_manager.active_provider is not None:
            chain_id = self.provider.chain_id
        elif chain_id is None:
            raise ValueError("Missing chain ID.")

        if chain_id not in self._custom_error_types:
            return set()

        errors = self._custom_error_types[chain_id]
        if address in errors:
            return errors[address]

        return set()

    def _cache_error(
        self, address: AddressType, error: type[CustomError], chain_id: Optional[int] = None
    ):
        if chain_id is None and self.network_manager.active_provider is not None:
            chain_id = self.provider.chain_id
        elif chain_id is None:
            raise ValueError("Missing chain ID.")

        if chain_id not in self._custom_error_types:
            self._custom_error_types[chain_id] = {address: set()}
        elif address not in self._custom_error_types[chain_id]:
            self._custom_error_types[chain_id][address] = set()

        self._custom_error_types[chain_id][address].add(error)

    def __getitem__(self, address: AddressType) -> ContractType:
        contract_type = self.get(address)
        if not contract_type:
            # Create error message from custom exception cls.
            err = ContractNotFoundError(
                address, self.provider.network.explorer is not None, self.provider.network_choice
            )
            # Must raise KeyError.
            raise KeyError(str(err))

        return contract_type

    def get_multiple(
        self, addresses: Collection[AddressType], concurrency: Optional[int] = None
    ) -> dict[AddressType, ContractType]:
        """
        Get contract types for all given addresses.

        Args:
            addresses (list[AddressType): A list of addresses to get contract types for.
            concurrency (Optional[int]): The number of threads to use. Defaults to
              ``min(4, len(addresses))``.

        Returns:
            dict[AddressType, ContractType]: A mapping of addresses to their respective
            contract types.
        """
        if not addresses:
            logger.warning("No addresses provided.")
            return {}

        def get_contract_type(addr: AddressType):
            addr = self.conversion_manager.convert(addr, AddressType)
            ct = self.get(addr)

            if not ct:
                logger.warning(f"Failed to locate contract at '{addr}'.")
                return addr, None
            else:
                return addr, ct

        converted_addresses: list[AddressType] = []
        for address in converted_addresses:
            if not self.conversion_manager.is_type(address, AddressType):
                converted_address = self.conversion_manager.convert(address, AddressType)
                converted_addresses.append(converted_address)
            else:
                converted_addresses.append(address)

        contract_types = {}
        default_max_threads = 4
        max_threads = (
            concurrency
            if concurrency is not None
            else min(len(addresses), default_max_threads) or default_max_threads
        )
        with ThreadPoolExecutor(max_workers=max_threads) as pool:
            for address, contract_type in pool.map(get_contract_type, addresses):
                if contract_type is None:
                    continue

                contract_types[address] = contract_type

        return contract_types

    @nonreentrant(key_fn=lambda *args, **kwargs: args[1])
    def get(
        self,
        address: AddressType,
        default: Optional[ContractType] = None,
        fetch_from_explorer: bool = True,
    ) -> Optional[ContractType]:
        """
        Get a contract type by address.
        If the contract is cached, it will return the contract from the cache.
        Otherwise, if on a live network, it fetches it from the
        :class:`~ape.api.explorers.ExplorerAPI`.

        Args:
            address (AddressType): The address of the contract.
            default (Optional[ContractType]): A default contract when none is found.
              Defaults to ``None``.
            fetch_from_explorer (bool): Set to ``False`` to avoid fetching from an
              explorer. Defaults to ``True``. Only fetches if it needs to (uses disk
              & memory caching otherwise).

        Returns:
            Optional[ContractType]: The contract type if it was able to get one,
              otherwise the default parameter.
        """
        try:
            address_key: AddressType = self.conversion_manager.convert(address, AddressType)
        except ConversionError:
            if not address.startswith("0x"):
                # Still raise conversion errors for ENS and such.
                raise

            # In this case, it at least _looked_ like an address.
            return None

        if contract_type := self.contract_types[address_key]:
            if default and default != contract_type:
                # Replacing contract type
                self.contract_types[address_key] = default
                return default

            return contract_type

        else:
            # Contract is not cached yet. Check broader sources, such as an explorer.
            # First, detect if this is a proxy.
            if not (proxy_info := self.proxy_infos[address_key]):
                if proxy_info := self.provider.network.ecosystem.get_proxy_info(address_key):
                    self.proxy_infos[address_key] = proxy_info

            if proxy_info:
                # Contract is a proxy.
                implementation_contract_type = self.get(proxy_info.target, default=default)
                proxy_contract_type = (
                    self._get_contract_type_from_explorer(address_key)
                    if fetch_from_explorer
                    else None
                )
                if proxy_contract_type:
                    contract_type_to_cache = _get_combined_contract_type(
                        proxy_contract_type, proxy_info, implementation_contract_type
                    )
                else:
                    contract_type_to_cache = implementation_contract_type

                self.contract_types[address_key] = contract_type_to_cache
                return contract_type_to_cache

            if not self.provider.get_code(address_key):
                if default:
                    self.contract_types[address_key] = default

                return default

            # Also gets cached to disk for faster lookup next time.
            if fetch_from_explorer:
                contract_type = self._get_contract_type_from_explorer(address_key)

        # Cache locally for faster in-session look-up.
        if contract_type:
            self.contract_types[address_key] = contract_type
        elif default:
            self.contract_types[address_key] = default
            return default

        return contract_type

    @classmethod
    def get_container(cls, contract_type: ContractType) -> ContractContainer:
        """
        Get a contract container for the given contract type.

        Args:
            contract_type (ContractType): The contract type to wrap.

        Returns:
            ContractContainer: A container object you can deploy.
        """

        return ContractContainer(contract_type)

    def instance_at(
        self,
        address: Union[str, AddressType],
        contract_type: Optional[ContractType] = None,
        txn_hash: Optional[Union[str, "HexBytes"]] = None,
        abi: Optional[Union[list[ABI], dict, str, Path]] = None,
        fetch_from_explorer: bool = True,
    ) -> ContractInstance:
        """
        Get a contract at the given address. If the contract type of the contract is known,
        either from a local deploy or a :class:`~ape.api.explorers.ExplorerAPI`, it will use that
        contract type. You can also provide the contract type from which it will cache and use
        next time.

        Raises:
            TypeError: When passing an invalid type for the `contract_type` arguments
              (expects `ContractType`).
            :class:`~ape.exceptions.ContractNotFoundError`: When the contract type is not found.

        Args:
            address (Union[str, AddressType]): The address of the plugin. If you are using the ENS
              plugin, you can also provide an ENS domain name.
            contract_type (Optional[``ContractType``]): Optionally provide the contract type
              in case it is not already known.
            txn_hash (Optional[Union[str, HexBytes]]): The hash of the transaction responsible for
              deploying the contract, if known. Useful for publishing. Defaults to ``None``.
            abi (Optional[Union[list[ABI], dict, str, Path]]): Use an ABI str, dict, path,
              or ethpm models to create a contract instance class.
            fetch_from_explorer (bool): Set to ``False`` to avoid fetching from the explorer.
              Defaults to ``True``. Won't fetch unless it needs to (uses disk & memory caching
              first).

        Returns:
            :class:`~ape.contracts.base.ContractInstance`
        """
        if contract_type and not isinstance(contract_type, ContractType):
            prefix = f"Expected type '{ContractType.__name__}' for argument 'contract_type'"
            try:
                suffix = f"; Given '{type(contract_type).__name__}'."
            except Exception:
                suffix = "."

            raise TypeError(f"{prefix}{suffix}")

        try:
            contract_address = self.conversion_manager.convert(address, AddressType)
        except ConversionError:
            # Attempt as str.
            raise ValueError(f"Unknown address value '{address}'.")

        try:
            # Always attempt to get an existing contract type to update caches
            contract_type = self.get(
                contract_address, default=contract_type, fetch_from_explorer=fetch_from_explorer
            )
        except Exception as err:
            if contract_type or abi:
                # If a default contract type was provided, don't error and use it.
                logger.error(str(err))
            else:
                raise  # Current exception

        if abi:
            # if the ABI is a str then convert it to a JSON dictionary.
            if isinstance(abi, Path) or (
                isinstance(abi, str) and "{" not in abi and Path(abi).is_file()
            ):
                # Handle both absolute and relative paths
                abi_path = Path(abi)
                if not abi_path.is_absolute():
                    abi_path = self.local_project.path / abi

                try:
                    abi = json.loads(abi_path.read_text())
                except Exception as err:
                    if contract_type:
                        # If a default contract type was provided, don't error and use it.
                        logger.error(str(err))
                    else:
                        raise  # Current exception

            elif isinstance(abi, str):
                # JSON str
                try:
                    abi = json.loads(abi)
                except Exception as err:
                    if contract_type:
                        # If a default contract type was provided, don't error and use it.
                        logger.error(str(err))
                    else:
                        raise  # Current exception

            # If the ABI was a str, it should be a list now.
            if isinstance(abi, list):
                contract_type = ContractType(abi=abi)

                # Ensure we cache the contract-types from ABI!
                self[contract_address] = contract_type

            else:
                raise TypeError(
                    f"Invalid ABI type '{type(abi)}', expecting str, list[ABI] or a JSON file."
                )

        if not contract_type:
            raise ContractNotFoundError(
                contract_address,
                self.provider.network.explorer is not None,
                self.provider.network_choice,
            )

        if not txn_hash:
            # Check for txn_hash in deployments.
            contract_name = getattr(contract_type, "name", f"{contract_type}") or ""
            deployments = self.deployments[contract_name]
            for deployment in deployments[::-1]:
                if deployment.address == contract_address and deployment.transaction_hash:
                    txn_hash = deployment.transaction_hash
                    break

        return ContractInstance(contract_address, contract_type, txn_hash=txn_hash)

    @classmethod
    def instance_from_receipt(
        cls, receipt: "ReceiptAPI", contract_type: ContractType
    ) -> ContractInstance:
        """
        A convenience method for creating instances from receipts.

        Args:
            receipt (:class:`~ape.api.transactions.ReceiptAPI`): The receipt.
            contract_type (ContractType): The deployed contract type.

        Returns:
            :class:`~ape.contracts.base.ContractInstance`
        """
        # NOTE: Mostly just needed this method to avoid a local import.
        return ContractInstance.from_receipt(receipt, contract_type)

    def get_deployments(self, contract_container: ContractContainer) -> list[ContractInstance]:
        """
        Retrieves previous deployments of a contract container or contract type.
        Locally deployed contracts are saved for the duration of the script and read from
        ``_local_deployments_mapping``, while those deployed on a live network are written to
        disk in ``deployments_map.json``.

        Args:
            contract_container (:class:`~ape.contracts.ContractContainer`): The
              ``ContractContainer`` with deployments.

        Returns:
            list[:class:`~ape.contracts.ContractInstance`]: Returns a list of contracts that
            have been deployed.
        """
        contract_type = contract_container.contract_type
        if not (contract_name := contract_type.name or ""):
            return []

        config_deployments = self._get_config_deployments(contract_name)
        if not (deployments := [*config_deployments, *self.deployments[contract_name]]):
            return []

        instances: list[ContractInstance] = []
        for deployment in deployments:
            instance = ContractInstance(
                deployment.address, contract_type, txn_hash=deployment.transaction_hash
            )
            instances.append(instance)

        return instances

    def _get_config_deployments(self, contract_name: str) -> list[Deployment]:
        if not self.network_manager.connected:
            return []

        ecosystem_name = self.provider.network.ecosystem.name
        network_name = self.provider.network.name
        all_config_deployments = (
            self.config_manager.deployments if self.config_manager.deployments else {}
        )
        ecosystem_deployments = all_config_deployments.get(ecosystem_name, {})
        network_deployments = ecosystem_deployments.get(network_name, {})
        return [
            Deployment(address=c["address"], transaction_hash=c.get("transaction_hash"))
            for c in network_deployments
            if c["contract_type"] == contract_name
        ]

    def clear_local_caches(self):
        """
        Reset local caches to a blank state.
        """
        if self.network_manager.connected:
            for cache in (
                self.contract_types,
                self.proxy_infos,
                self.contract_creations,
                self.blueprints,
            ):
                cache.memory = {}

        self.deployments.clear_local()

    def _get_contract_type_from_explorer(self, address: AddressType) -> Optional[ContractType]:
        if not self.provider.network.explorer:
            return None

        try:
            contract_type = self.provider.network.explorer.get_contract_type(address)
        except Exception as err:
            explorer_name = self.provider.network.explorer.name
            if "rate limit" in str(err).lower():
                # Don't show any additional error message during rate limit errors,
                # if it can be helped, as it may scare users into thinking their
                # contracts are not verified.
                message = str(err)
            else:
                # Carefully word this message in a way that doesn't hint at
                # any one specific reason, such as un-verified source code,
                # which is potentially a scare for users.
                message = (
                    f"Attempted to retrieve contract type from explorer '{explorer_name}' "
                    f"from address '{address}' but encountered an exception: {err}\n"
                )

            logger.error(message)
            return None

        if contract_type:
            # Cache contract so faster look-up next time.
            self.contract_types[address] = contract_type

        return contract_type


def _get_combined_contract_type(
    proxy_contract_type: ContractType,
    proxy_info: ProxyInfoAPI,
    implementation_contract_type: ContractType,
) -> ContractType:
    proxy_abis = [
        abi for abi in proxy_contract_type.abi if abi.type in ("error", "event", "function")
    ]

    # Include "hidden" ABIs, such as Safe's `masterCopy()`.
    if proxy_info.abi and proxy_info.abi.signature not in [
        abi.signature for abi in implementation_contract_type.abi
    ]:
        proxy_abis.append(proxy_info.abi)

    combined_contract_type = implementation_contract_type.model_copy(deep=True)
    combined_contract_type.abi.extend(proxy_abis)
    return combined_contract_type
