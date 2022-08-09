import json
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable, Collection, Dict, Iterator, List, Optional, Tuple, Union, cast

import pandas as pd
from ethpm_types import ContractType

from ape.api import BlockAPI, ReceiptAPI
from ape.api.address import BaseAddress
from ape.api.networks import LOCAL_NETWORK_NAME, NetworkAPI, ProxyInfoAPI
from ape.api.query import BlockQuery, validate_and_expand_columns
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import ChainError, ConversionError, UnknownSnapshotError
from ape.logging import logger
from ape.managers.base import BaseManager
from ape.types import AddressType, BlockID, SnapshotID
from ape.utils import cached_property


class BlockContainer(BaseManager):
    """
    A list of blocks on the chain.

    Usages example::

        from ape import chain

        latest_block = chain.blocks[-1]

    """

    @property
    def head(self) -> BlockAPI:
        """
        The latest block.
        """

        return self._get_block("latest")

    @property
    def height(self) -> int:
        """
        The latest block number.
        """
        if self.head.number is None:
            raise ChainError("Latest block has no number.")

        return self.head.number

    @property
    def network_confirmations(self) -> int:
        return self.provider.network.required_confirmations

    def __getitem__(self, block_number: int) -> BlockAPI:
        """
        Get a block by number. Negative numbers start at the chain head and
        move backwards. For example, ``-1`` would be the latest block and
        ``-2`` would be the block prior to that one, and so on.

        Args:
            block_number (int): The number of the block to get.

        Returns:
            :class:`~ape.api.providers.BlockAPI`
        """

        if block_number < 0:
            block_number = len(self) + block_number

        return self._get_block(block_number)

    def __len__(self) -> int:
        """
        The number of blocks in the chain.

        Returns:
            int
        """

        return self.height + 1

    def __iter__(self) -> Iterator[BlockAPI]:
        """
        Iterate over all the current blocks.

        Returns:
            Iterator[:class:`~ape.api.providers.BlockAPI`]
        """

        return self.range(len(self))

    def query(
        self,
        *columns: List[str],
        start_block: int = 0,
        stop_block: Optional[int] = None,
        step: int = 1,
        engine_to_use: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        A method for querying blocks and returning an Iterator. If you
        do not provide a starting block, the 0 block is assumed. If you do not
        provide a stopping block, the last block is assumed. You can pass
        ``engine_to_use`` to short-circuit engine selection.

        Raises:
            :class:`~ape.exceptions.ChainError`: When ``stop_block`` is greater
              than the chain length.

        Args:
            columns (List[str]): columns in the DataFrame to return
            start_block (int): The first block, by number, to include in the
              query. Defaults to 0.
            stop_block (Optional[int]): The last block, by number, to include
              in the query. Defaults to the latest block.
            step (int): The number of blocks to iterate between block numbers.
              Defaults to ``1``.
            engine_to_use (Optional[str]): query engine to use, bypasses query
              engine selection algorithm.

        Returns:
            pd.DataFrame
        """

        if start_block < 0:
            start_block = len(self) + start_block

        if stop_block is None:
            stop_block = self.height

        elif stop_block < 0:
            stop_block = len(self) + stop_block

        elif stop_block > len(self):
            raise ChainError(
                f"'stop={stop_block}' cannot be greater than the chain length ({self.height})."
            )

        query = BlockQuery(
            columns=list(self.head.__fields__),
            start_block=start_block,
            stop_block=stop_block,
            step=step,
        )

        blocks = self.query_manager.query(query, engine_to_use=engine_to_use)
        data = map(lambda val: val.dict(by_alias=False), blocks)

        # NOTE: Allow any columns from ecosystem's BlockAPI class
        # TODO: fetch the block fields from EcosystemAPI
        columns = validate_and_expand_columns(columns, list(self.head.__fields__))  # type: ignore
        return pd.DataFrame(columns=columns, data=data)

    def range(
        self,
        start_or_stop: int,
        stop: Optional[int] = None,
        step: int = 1,
        engine_to_use: Optional[str] = None,
    ) -> Iterator[BlockAPI]:
        """
        Iterate over blocks. Works similarly to python ``range()``.

        Raises:
            :class:`~ape.exceptions.ChainError`: When ``stop`` is greater
                than the chain length.
            :class:`~ape.exceptions.ChainError`: When ``stop`` is less
                than ``start_block``.
            :class:`~ape.exceptions.ChainError`: When ``stop`` is less
                than 0.
            :class:`~ape.exceptions.ChainError`: When ``start`` is less
                than 0.

        Args:
            start_or_stop (int): When given just a single value, it is the stop.
              Otherwise, it is the start. This mimics the behavior of ``range``
              built-in Python function.
            stop (Optional[int]): The block number to stop before. Also the total
              number of blocks to get. If not setting a start value, is set by
              the first argument.
            step (Optional[int]): The value to increment by. Defaults to ``1``.
             number of blocks to get. Defaults to the latest block.
            engine_to_use (Optional[str]): query engine to use, bypasses query
              engine selection algorithm.

        Returns:
            Iterator[:class:`~ape.api.providers.BlockAPI`]
        """

        if stop is None:
            stop = start_or_stop
            start = 0
        else:
            start = start_or_stop

        if stop > len(self):
            raise ChainError(
                f"'stop={stop}' cannot be greater than the chain length ({len(self)}). "
                f"Use '{self.poll_blocks.__name__}()' to wait for future blocks."
            )

        # Note: the range `stop_block` is a non-inclusive stop, while the
        #       `.query` method uses an inclusive stop, so we must adjust downwards.
        query = BlockQuery(
            columns=list(self.head.__fields__),  # TODO: fetch the block fields from EcosystemAPI
            start_block=start,
            stop_block=stop - 1,
            step=step,
        )

        blocks = self.query_manager.query(query, engine_to_use=engine_to_use)
        yield from cast(Iterator[BlockAPI], blocks)

    def poll_blocks(
        self,
        start_block: Optional[int] = None,
        stop_block: Optional[int] = None,
        required_confirmations: Optional[int] = None,
        new_block_timeout: Optional[int] = None,
    ) -> Iterator[BlockAPI]:
        """
        Poll new blocks. Optionally set a start block to include historical blocks.
        **NOTE**: This is a daemon method; it does not terminate unless an exception occurrs
        or a ``stop`` is given.

        Usage example::

            from ape import chain

            for new_block in chain.blocks.poll_blocks():
                print(f"New block found: number={new_block.number}")

        Args:
            start_block (Optional[int]): The block number to start with. Defaults to the pending
              block number.
            stop_block (Optional[int]): Optionally set a future block number to stop at.
              Defaults to never-ending.
            required_confirmations (Optional[int]): The amount of confirmations to wait
              before yielding the block. The more confirmations, the less likely a reorg will occur.
              Defaults to the network's configured required confirmations.
            new_block_timeout (Optional[float]): The amount of time to wait for a new block before
              timing out. Defaults to 10 seconds for local networks or ``50 * block_time`` for live
              networks.

        Returns:
            Iterator[:class:`~ape.api.providers.BlockAPI`]
        """
        network_name = self.provider.network.name
        block_time = self.provider.network.block_time
        timeout = (
            (
                10.0
                if network_name == LOCAL_NETWORK_NAME or network_name.endswith("-fork")
                else 50 * block_time
            )
            if new_block_timeout is None
            else new_block_timeout
        )

        if required_confirmations is None:
            required_confirmations = self.network_confirmations

        if stop_block is not None and stop_block <= self.chain_manager.blocks.height:
            raise ValueError("'stop' argument must be in the future.")

        # Get number of last block with the necessary amount of confirmations.
        latest_confirmed_block_number = self.height - required_confirmations
        has_yielded_before_reorg = False

        if start_block is not None:
            # Front-load historically confirmed blocks.
            yield from self.range(start_block, latest_confirmed_block_number + 1)
            has_yielded_before_reorg = True

        time.sleep(block_time)
        time_since_last = time.time()

        def _try_timeout():
            if time.time() - time_since_last > timeout:
                time_waited = round(time.time() - time_since_last, 4)
                raise ChainError(f"Timed out waiting for new block (time_waited={time_waited}).")

        while True:
            confirmable_block_number = self.height - required_confirmations
            if (
                confirmable_block_number < latest_confirmed_block_number
                and has_yielded_before_reorg
            ):
                logger.error(
                    "Chain has reorganized since returning the last block. "
                    "Try adjusting the required network confirmations."
                )
                # Reset to prevent timeout
                time_since_last = time.time()

            elif confirmable_block_number >= latest_confirmed_block_number:
                # Yield all missed confirmable blocks
                new_blocks_count = (confirmable_block_number - latest_confirmed_block_number) + 1
                _try_timeout()
                if not new_blocks_count:
                    continue

                block_num = latest_confirmed_block_number
                for i in range(new_blocks_count):
                    block = self._get_block(block_num)

                    yield block
                    time_since_last = time.time()

                    if stop_block and block.number == stop_block:
                        return

                    block_num += 1

                has_yielded_before_reorg = True
                latest_confirmed_block_number = block_num

            else:
                _try_timeout()

            has_yielded_before_reorg = False
            time.sleep(block_time)

    def _get_block(self, block_id: BlockID) -> BlockAPI:
        return self.provider.get_block(block_id)


class AccountHistory(BaseManager):
    """
    A container mapping account addresses to the transaction from the active session.
    """

    _map: Dict[AddressType, List[ReceiptAPI]] = {}

    @cached_property
    def _convert(self) -> Callable:

        return self.conversion_manager.convert

    def __getitem__(self, address: Union[BaseAddress, AddressType, str]) -> List[ReceiptAPI]:
        """
        Get the list of transactions from the active session for the given address.

        Args:
            address (``AddressType``): The sender of the desired transactions.

        Returns:
            List[:class:`~ape.api.transactions.TransactionAPI`]: The list of transactions. If there
            are no recorded transactions, returns an empty list.
        """

        address_key: AddressType = self._convert(address, AddressType)
        explorer = self.provider.network.explorer
        explorer_receipts = (
            [r for r in explorer.get_account_transactions(address_key)] if explorer else []
        )
        for receipt in explorer_receipts:
            if receipt.txn_hash not in [r.txn_hash for r in self._map.get(address_key, [])]:
                self.append(receipt)

        return self._map.get(address_key, [])

    def __iter__(self) -> Iterator[AddressType]:
        """
        Iterate through the accounts listed in the history map.

        Returns:
            List[str]
        """

        yield from self._map

    def items(self) -> Iterator[Tuple[AddressType, List[ReceiptAPI]]]:
        """
        Iterate through the list of address-types to list of transaction receipts.

        Returns:
            Iterator[Tuple[``AddressType``, :class:`~ape.api.transactions.ReceiptAPI`]]
        """
        yield from self._map.items()

    def append(self, txn_receipt: ReceiptAPI):
        """
        Add a transaction to the stored list for the given account address.

        Raises:
            :class:`~ape.exceptions.ChainError`: When trying to append a transaction
              receipt that is already in the list.

        Args:
            txn_receipt (:class:`~ape.api.transactions.ReceiptAPI`): The transaction receipt.
              **NOTE**: The receipt is accessible in the list returned from
              :meth:`~ape.managers.chain.AccountHistory.__getitem__`.
        """
        address = self._convert(txn_receipt.sender, AddressType)
        if address not in self._map:
            self._map[address] = [txn_receipt]
            return

        if txn_receipt.txn_hash in [r.txn_hash for r in self._map[address]]:
            raise ChainError(f"Transaction '{txn_receipt.txn_hash}' already known.")

        self._map[address].append(txn_receipt)

    def revert_to_block(self, block_number: int):
        """
        Remove all receipts past the given block number.

        Args:
            block_number (int): The block number to revert to.
        """

        self._map = {
            a: [r for r in receipts if r.block_number <= block_number]
            for a, receipts in self.items()
        }


class ContractCache(BaseManager):
    """
    A collection of cached contracts. Contracts can be cached in two ways:

    1. An in-memory cache of locally deployed contracts
    2. A cache of contracts per network (only permanent networks are stored this way)

    When retrieving a contract, if a :class:`~ape.api.explorers.ExplorerAPI` is used,
    it will be cached to disk for faster look-up next time.
    """

    _local_contract_types: Dict[AddressType, ContractType] = {}
    _local_proxies: Dict[AddressType, ProxyInfoAPI] = {}
    _local_deployments_mapping: Dict[str, Dict] = {}

    @property
    def _network(self) -> NetworkAPI:
        return self.provider.network

    @property
    def _ecosystem_name(self) -> str:
        return self._network.ecosystem.name

    @property
    def _is_live_network(self) -> bool:
        return self._network.name != LOCAL_NETWORK_NAME and not self._network.name.endswith("-fork")

    @property
    def _data_network_name(self) -> str:
        return self._network.name.replace("-fork", "")

    @property
    def _contract_types_cache(self) -> Path:
        return self._network.ecosystem.data_folder / self._data_network_name / "contract_types"

    @property
    def _deployments_mapping_cache(self) -> Path:
        return self._network.ecosystem.data_folder / "deployments_map.json"

    @property
    def _proxy_info_cache(self) -> Path:
        return self._network.ecosystem.data_folder / self._data_network_name / "proxy_info"

    @property
    def _full_deployments(self) -> Dict:
        deployments = self._local_deployments_mapping
        if self._is_live_network:
            deployments = {**deployments, **self._load_deployments_cache()}

        return deployments

    @property
    def _deployments(self) -> Dict:
        deployments = self._full_deployments
        return deployments.get(self._ecosystem_name, {}).get(self._data_network_name, {})

    @_deployments.setter
    def _deployments(self, value):
        deployments = self._full_deployments
        ecosystem_deployments = self._local_deployments_mapping.get(self._ecosystem_name, {})
        ecosystem_deployments[self._data_network_name] = value
        self._local_deployments_mapping[self._ecosystem_name] = ecosystem_deployments

        if self._is_live_network:
            self._write_deployments_mapping(
                {**deployments, self._ecosystem_name: ecosystem_deployments}
            )

    def __setitem__(self, address: AddressType, contract_type: ContractType):
        """
        Cache the given contract type. Contracts are cached in memory per session.
        In live networks, contracts also get cached to disk at
        ``.ape/{ecosystem_name}/{network_name}/contract_types/{address}.json``
        for faster look-up next time.

        Args:
            address (AddressType): The on-chain address of the contract.
            contract_type (ContractType): The contract's type.
        """

        self._cache_contract_type(address, contract_type)

        # NOTE: The txn_hash is not included when caching this way.
        self._cache_deployment(address, contract_type)

    def cache_deployment(self, contract_instance: ContractInstance):
        """
        Cache the given contract instance's type and deployment information.

        Args:
            contract_instance (:class:`~ape.contracts.base.ContractInstance`): The contract
              to cache.
        """

        address = contract_instance.address
        contract_type = contract_instance.contract_type
        txn_hash = contract_instance.txn_hash
        self._cache_contract_type(address, contract_type)
        self._cache_deployment(address, contract_type, txn_hash)

    def _cache_contract_type(self, address: AddressType, contract_type: ContractType):
        self._local_contract_types[address] = contract_type
        if self._is_live_network:
            # NOTE: We don't cache forked network contracts in this method to avoid caching
            # deployments from a fork. However, if you retrieve a contract from an explorer
            # when using a forked network, it will still get cached to disk.
            self._cache_contract_to_disk(address, contract_type)

    def _cache_deployment(
        self, address: AddressType, contract_type: ContractType, txn_hash: Optional[str] = None
    ):
        deployments = self._deployments
        contract_deployments = deployments.get(contract_type.name, [])
        new_deployment = {"address": address, "transaction_hash": txn_hash}
        contract_deployments.append(new_deployment)
        self._deployments = {**deployments, contract_type.name: contract_deployments}

    def __getitem__(self, address: AddressType) -> ContractType:
        contract_type = self.get(address)
        if not contract_type:
            raise IndexError(f"No contract type found at address '{address}'.")

        return contract_type

    def get_multiple(
        self, addresses: Collection[AddressType], concurrency: Optional[int] = None
    ) -> Dict[AddressType, ContractType]:
        """
        Get contract types for all given addresses.

        Args:
            addresses (List[AddressType): A list of addresses to get contract types for.
            concurrency (Optional[int]): The number of threads to use. Defaults to
              ``min(4, len(addresses))``.

        Returns:
            Dict[AddressType, ContractType]: A mapping of addresses to their respective
            contract types.
        """

        def get_contract_type(address: AddressType):
            address = self.conversion_manager.convert(address, AddressType)
            contract_type = self.get(address)

            if not contract_type:
                logger.warning(f"Failed to locate contract at '{address}'.")
                return address, None
            else:
                return address, contract_type

        addresses = [self.conversion_manager.convert(a, AddressType) for a in addresses]
        contract_types = {}
        num_threads = concurrency if concurrency is not None else min(len(addresses), 4)
        with ThreadPoolExecutor(num_threads) as pool:
            for address, contract_type in pool.map(get_contract_type, addresses):
                if contract_type is None:
                    continue

                contract_types[address] = contract_type

        return contract_types

    def get(
        self, address: AddressType, default: Optional[ContractType] = None
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

        Returns:
            Optional[ContractType]: The contract type if it was able to get one,
              otherwise the default parameter.
        """

        address_key: AddressType = self.conversion_manager.convert(address, AddressType)
        contract_type = self._local_contract_types.get(address_key)
        if contract_type:
            if default and default != contract_type:
                # Replacing contract type
                self._local_contract_types[address_key] = default
                return default

            return contract_type

        if self._network.name == LOCAL_NETWORK_NAME:
            # Don't check disk-cache or explorer when using local
            if default:
                self._local_contract_types[address_key] = default

            return default

        contract_type = self._get_contract_type_from_disk(address_key)
        if not contract_type:
            # Contract could be a minimal proxy
            proxy_info = self._local_proxies.get(address_key) or self._get_proxy_info_from_disk(
                address_key
            )

            if not proxy_info:
                proxy_info = self.provider.network.ecosystem.get_proxy_info(address_key)
                if proxy_info and self._is_live_network:
                    self._cache_proxy_info_to_disk(address_key, proxy_info)

            if proxy_info:
                self._local_proxies[address_key] = proxy_info
                return self.get(proxy_info.target)

            if not self.provider.get_code(address_key):
                if default:
                    self._local_contract_types[address_key] = default
                    self._cache_contract_to_disk(address_key, default)

                return default

            # Also gets cached to disk for faster lookup next time.
            contract_type = self._get_contract_type_from_explorer(address_key)

        # Cache locally for faster in-session look-up.
        if contract_type:
            self._local_contract_types[address_key] = contract_type

        if not contract_type:
            if default:
                self._local_contract_types[address_key] = default
                self._cache_contract_to_disk(address_key, default)

            return default

        if default and default != contract_type:
            # Replacing contract type
            self._local_contract_types[address_key] = default
            self._cache_contract_to_disk(address_key, default)
            return default

        return contract_type

    def get_container(self, contract_type: ContractType) -> ContractContainer:
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
        address: Union[str, "AddressType"],
        contract_type: Optional[ContractType] = None,
        txn_hash: Optional[str] = None,
    ) -> ContractInstance:
        """
        Get a contract at the given address. If the contract type of the contract is known,
        either from a local deploy or a :class:`~ape.api.explorers.ExplorerAPI`, it will use that
        contract type. You can also provide the contract type from which it will cache and use
        next time.

        Raises:
            TypeError: When passing an invalid type for the `contract_type` arguments
              (expects `ContractType`).

        Args:
            address (Union[str, AddressType]): The address of the plugin. If you are using the ENS
              plugin, you can also provide an ENS domain name.
            contract_type (Optional[``ContractType``]): Optionally provide the contract type
              in case it is not already known.

        Returns:
            :class:`~ape.contracts.base.ContractInstance`
        """

        if contract_type and not isinstance(contract_type, ContractType):
            raise TypeError("Expected type 'ContractType' for argument 'contract_type'.")
        try:
            address = self.conversion_manager.convert(address, AddressType)
        except ConversionError:
            address = address

        address = self.provider.network.ecosystem.decode_address(address)
        contract_type = self.get(address, default=contract_type)
        if not txn_hash and contract_type:
            # Check for txn_hash in deployments.
            deployments = self._deployments.get(contract_type.name) or []
            for deployment in deployments:
                if deployment["address"] == address:
                    txn_hash = deployment.get("transaction_hash")
                    break

        if not contract_type:
            raise ChainError(f"Failed to get contract type for address '{address}'.")

        elif not isinstance(contract_type, ContractType):
            raise TypeError(
                f"Expected type '{ContractType.__name__}' for argument 'contract_type'."
            )

        return ContractInstance(address, contract_type, txn_hash=txn_hash)

    def get_deployments(self, contract_container: ContractContainer) -> List[ContractInstance]:
        """
        Retrieves previous deployments of a contract container or contract type.
        Locally deployed contracts are saved for the duration of the script and read from
        ``_local_deployments_mapping``, while those deployed on a live network are written to
        disk in ``deployments_map.json``.

        Args:
            contract_container (:class:`~ape.contracts.ContractContainer`): The
              ``ContractContainer`` with deployments.

        Returns:
            List[:class:`~ape.contracts.ContractInstance`]: Returns a list of contracts that
            have been deployed.
        """

        contract_type = contract_container.contract_type
        contract_name = contract_type.name
        if not contract_name:
            return []

        deployments = self._deployments.get(contract_name, [])
        if not deployments:
            return []

        if isinstance(deployments[0], str):
            # TODO: Remove this migration logic >= version 0.6.0
            logger.debug("Migrating 'deployments_map.json'.")
            deployments = [{"address": a} for a in deployments]
            self._deployments = {
                **self._deployments,
                contract_type.name: deployments,
            }

        instances: List[ContractInstance] = []
        for deployment in deployments:
            address = deployment["address"]
            txn_hash = deployment.get("transaction_hash")
            instance = ContractInstance(address, contract_type, txn_hash=txn_hash)
            instances.append(instance)

        return instances

    def _get_contract_type_from_disk(self, address: AddressType) -> Optional[ContractType]:
        address_file = self._contract_types_cache / f"{address}.json"
        if not address_file.is_file():
            return None

        return ContractType.parse_raw(address_file.read_text())

    def _get_proxy_info_from_disk(self, address: AddressType) -> Optional[ProxyInfoAPI]:
        address_file = self._proxy_info_cache / f"{address}.json"
        if not address_file.is_file():
            return None

        return ProxyInfoAPI.parse_raw(address_file.read_text())

    def _get_contract_type_from_explorer(self, address: AddressType) -> Optional[ContractType]:
        if not self._network.explorer:
            return None

        try:
            contract_type = self._network.explorer.get_contract_type(address)
        except Exception as err:
            logger.error(f"Unable to fetch contract type at '{address}' from explorer.\n{err}")
            return None

        if contract_type:
            # Cache contract so faster look-up next time.
            self._cache_contract_to_disk(address, contract_type)

        return contract_type

    def _cache_contract_to_disk(self, address: AddressType, contract_type: ContractType):
        self._contract_types_cache.mkdir(exist_ok=True, parents=True)
        address_file = self._contract_types_cache / f"{address}.json"
        address_file.write_text(contract_type.json())

    def _cache_proxy_info_to_disk(self, address: AddressType, proxy_info: ProxyInfoAPI):
        self._proxy_info_cache.mkdir(exist_ok=True, parents=True)
        address_file = self._proxy_info_cache / f"{address}.json"
        address_file.write_text(proxy_info.json())

    def _load_deployments_cache(self) -> Dict:
        return (
            json.loads(self._deployments_mapping_cache.read_text())
            if self._deployments_mapping_cache.exists()
            else {}
        )

    def _write_deployments_mapping(self, deployments_map: Dict):
        self._deployments_mapping_cache.parent.mkdir(exist_ok=True, parents=True)
        with self._deployments_mapping_cache.open("w") as fp:
            json.dump(deployments_map, fp, sort_keys=True, indent=2, default=sorted)


class ChainManager(BaseManager):
    """
    A class for managing the state of the active blockchain.
    Also handy for querying data about the chain and managing local caches.
    Access the chain manager singleton from the root ``ape`` namespace.

    Usage example::

        from ape import chain
    """

    _snapshots: List[SnapshotID] = []
    _chain_id_map: Dict[str, int] = {}
    _block_container_map: Dict[int, BlockContainer] = {}
    _account_history_map: Dict[int, AccountHistory] = {}
    contracts: ContractCache = ContractCache()

    @property
    def blocks(self) -> BlockContainer:
        """
        The list of blocks on the chain.
        """
        if self.chain_id not in self._block_container_map:
            blocks = BlockContainer()
            self._block_container_map[self.chain_id] = blocks

        return self._block_container_map[self.chain_id]

    @property
    def account_history(self) -> AccountHistory:
        """
        A mapping of transactions from the active session to the account responsible.
        """
        if self.chain_id not in self._account_history_map:
            history = AccountHistory()
            self._account_history_map[self.chain_id] = history

        return self._account_history_map[self.chain_id]

    @property
    def chain_id(self) -> int:
        """
        The blockchain ID.
        See `ChainList <https://chainlist.org/>`__ for a comprehensive list of IDs.
        """

        network_name = self.provider.network.name
        if network_name not in self._chain_id_map:
            self._chain_id_map[network_name] = self.provider.chain_id

        return self._chain_id_map[network_name]

    @property
    def gas_price(self) -> int:
        """
        The price for what it costs to transact.
        """

        return self.provider.gas_price

    @property
    def base_fee(self) -> int:
        """
        The minimum value required to get your transaction included on the next block.
        Only providers that implement `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__
        will use this property.

        Raises:
            NotImplementedError: When this provider does not implement
              `EIP-1559 <https://eips.ethereum.org/EIPS/eip-1559>`__.
        """

        return self.provider.base_fee

    @property
    def pending_timestamp(self) -> int:
        """
        The current epoch time of the chain, as an ``int``.
        You can also set the timestamp for development purposes.

        Usage example::

            from ape import chain
            chain.pending_timestamp += 3600
        """

        return self.provider.get_block("pending").timestamp

    @pending_timestamp.setter
    def pending_timestamp(self, new_value: str):
        self.provider.set_timestamp(self.conversion_manager.convert(value=new_value, type=int))

    def __repr__(self) -> str:
        props = f"id={self.chain_id}" if self.network_manager.active_provider else "disconnected"
        return f"<{self.__class__.__name__} ({props})>"

    def snapshot(self) -> SnapshotID:
        """
        Record the current state of the blockchain with intent to later
        call the method :meth:`~ape.managers.chain.ChainManager.revert`
        to go back to this point. This method is for local networks only.

        Raises:
            NotImplementedError: When the active provider does not support
              snapshotting.

        Returns:
            :class:`~ape.types.SnapshotID`: The snapshot ID.
        """
        snapshot_id = self.provider.snapshot()
        if snapshot_id not in self._snapshots:
            self._snapshots.append(snapshot_id)

        return snapshot_id

    def restore(self, snapshot_id: Optional[SnapshotID] = None):
        """
        Regress the current call using the given snapshot ID.
        Allows developers to go back to a previous state.

        Raises:
            NotImplementedError: When the active provider does not support
              snapshotting.
            :class:`~ape.exceptions.UnknownSnapshotError`: When the snapshot ID is not cached.
            :class:`~ape.exceptions.ChainError`: When there are no snapshot IDs to select from.

        Args:
            snapshot_id (Optional[:class:`~ape.types.SnapshotID`]): The snapshot ID. Defaults
              to the most recent snapshot ID.
        """
        if snapshot_id is None and not self._snapshots:
            raise ChainError("There are no snapshots to revert to.")
        elif snapshot_id is None:
            snapshot_id = self._snapshots.pop()
        elif snapshot_id not in self._snapshots:
            raise UnknownSnapshotError(snapshot_id)
        else:
            snapshot_index = self._snapshots.index(snapshot_id)
            self._snapshots = self._snapshots[:snapshot_index]

        self.provider.revert(snapshot_id)
        self.account_history.revert_to_block(self.blocks.height)

    def mine(
        self,
        num_blocks: int = 1,
        timestamp: Optional[int] = None,
        deltatime: Optional[int] = None,
    ) -> None:
        """
        Mine any given number of blocks.

        Raises:
            ValueError: When a timestamp AND a deltatime argument are both passed

        Args:
            num_blocks (int): Choose the number of blocks to mine.
                Defaults to 1 block.
            timestamp (Optional[int]): Designate a time (in seconds) to begin mining.
                Defaults to None.
            deltatime (Optional[int]): Designate a change in time (in seconds) to begin mining.
                Defaults to None
        """
        if timestamp and deltatime:
            raise ValueError("Cannot give both `timestamp` and `deltatime` arguments together.")
        if timestamp:
            self.pending_timestamp = timestamp
        elif deltatime:
            self.pending_timestamp += deltatime
        self.provider.mine(num_blocks)

    def set_balance(self, account: Union[BaseAddress, AddressType], amount: Union[int, str]):
        if isinstance(account, BaseAddress):
            account = account.address  # type: ignore

        if isinstance(amount, str) and len(str(amount).split(" ")) > 1:
            # Support values like "1000 ETH".
            amount = self.conversion_manager.convert(amount, int)
        elif isinstance(amount, str):
            # Support hex strings
            amount = int(amount, 16)

        return self.provider.set_balance(account, amount)
