import json
from collections import defaultdict
from collections.abc import Collection, Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial, singledispatchmethod
from pathlib import Path
from statistics import mean, median
from typing import IO, Optional, Union, cast

import pandas as pd
from eth_pydantic_types import HexBytes
from ethpm_types import ABI, ContractType
from rich.box import SIMPLE
from rich.console import Console as RichConsole
from rich.table import Table

from ape.api.address import BaseAddress
from ape.api.networks import NetworkAPI, ProxyInfoAPI
from ape.api.providers import BlockAPI
from ape.api.query import (
    AccountTransactionQuery,
    BlockQuery,
    ContractCreation,
    ContractCreationQuery,
    extract_fields,
    validate_and_expand_columns,
)
from ape.api.transactions import ReceiptAPI
from ape.contracts import ContractContainer, ContractInstance
from ape.exceptions import (
    APINotImplementedError,
    ChainError,
    ContractNotFoundError,
    ConversionError,
    CustomError,
    ProviderNotConnectedError,
    QueryEngineError,
    TransactionNotFoundError,
    UnknownSnapshotError,
)
from ape.logging import get_rich_console, logger
from ape.managers.base import BaseManager
from ape.types.address import AddressType
from ape.types.trace import GasReport, SourceTraceback
from ape.types.vm import SnapshotID
from ape.utils.basemodel import BaseInterfaceModel
from ape.utils.misc import is_evm_precompile, is_zero_hex, log_instead_of_fail, nonreentrant


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
        return self.provider.get_block("latest")

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

        return self.provider.get_block(block_number)

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
        *columns: str,
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
            *columns (str): columns in the DataFrame to return
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
            columns=list(columns),
            start_block=start_block,
            stop_block=stop_block,
            step=step,
        )

        blocks = self.query_manager.query(query, engine_to_use=engine_to_use)
        columns: list[str] = validate_and_expand_columns(  # type: ignore
            columns, self.head.__class__
        )
        extraction = partial(extract_fields, columns=columns)
        data = map(lambda b: extraction(b), blocks)
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
            columns=list(self.head.model_fields),  # TODO: fetch the block fields from EcosystemAPI
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

        **NOTE**: When a chain reorganization occurs, this method logs an error and
        yields the missed blocks, even if they were previously yielded with different
        block numbers.

        **NOTE**: This is a daemon method; it does not terminate unless an exception occurs
        or a ``stop_block`` is given.

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

        if required_confirmations is None:
            required_confirmations = self.network_confirmations

        if stop_block is not None and stop_block <= self.chain_manager.blocks.height:
            raise ValueError("'stop' argument must be in the future.")

        # Get number of last block with the necessary amount of confirmations.
        block = None

        head_minus_confirms = self.height - required_confirmations
        if start_block is not None and start_block <= head_minus_confirms:
            # Front-load historical blocks.
            for block in self.range(start_block, head_minus_confirms + 1):
                yield block

        yield from self.provider.poll_blocks(
            stop_block=stop_block,
            required_confirmations=required_confirmations,
            new_block_timeout=new_block_timeout,
        )


class AccountHistory(BaseInterfaceModel):
    """
    A container mapping account addresses to the transaction from the active session.
    """

    address: AddressType
    """
    The address to get history for.
    """

    sessional: list[ReceiptAPI] = []
    """
    The receipts from the current Python session.
    """

    @property
    def outgoing(self) -> Iterator[ReceiptAPI]:
        """
        All outgoing transactions, from earliest to latest.
        """

        start_nonce = 0
        stop_nonce = len(self) - 1  # just to cache this value

        # TODO: Add ephemeral network sessional history to `ape-cache` instead,
        #       and remove this (replace with `yield from iter(self[:len(self)])`)
        for receipt in self.sessional:
            if receipt.nonce is None:
                # Not an on-chain receipt? idk - has only seen as anomaly in tests.
                continue

            elif receipt.nonce < start_nonce:
                raise QueryEngineError("Sessional history corrupted")

            elif receipt.nonce > start_nonce:
                # NOTE: There's a gap in our sessional history, so fetch from query engine
                yield from iter(self[start_nonce : receipt.nonce + 1])  # noqa: E203

            yield receipt
            start_nonce = receipt.nonce + 1  # start next loop on the next item

        if start_nonce != stop_nonce:
            # NOTE: there is no more session history, so just return query engine iterator
            yield from iter(self[start_nonce : stop_nonce + 1])  # noqa: E203

    def query(
        self,
        *columns: str,
        start_nonce: int = 0,
        stop_nonce: Optional[int] = None,
        engine_to_use: Optional[str] = None,
    ) -> pd.DataFrame:
        """
        A method for querying transactions made by an account and returning an Iterator.
        If you do not provide a starting nonce, the first transaction is assumed.
        If you do not provide a stopping block, the last transaction is assumed.
        You can pass ``engine_to_use`` to short-circuit engine selection.

        Raises:
            :class:`~ape.exceptions.ChainError`: When ``stop_nonce`` is greater
              than the account's current nonce.

        Args:
            *columns (str): columns in the DataFrame to return
            start_nonce (int): The first transaction, by nonce, to include in the
              query. Defaults to 0.
            stop_nonce (Optional[int]): The last transaction, by nonce, to include
              in the query. Defaults to the latest transaction.
            engine_to_use (Optional[str]): query engine to use, bypasses query
              engine selection algorithm.

        Returns:
            pd.DataFrame
        """

        if start_nonce < 0:
            start_nonce = len(self) + start_nonce

        if stop_nonce is None:
            stop_nonce = len(self)

        elif stop_nonce < 0:
            stop_nonce = len(self) + stop_nonce

        elif stop_nonce > len(self):
            raise ChainError(
                f"'stop={stop_nonce}' cannot be greater than account's current nonce ({len(self)})."
            )

        query = AccountTransactionQuery(
            columns=list(columns),
            account=self.address,
            start_nonce=start_nonce,
            stop_nonce=stop_nonce,
        )

        txns = self.query_manager.query(query, engine_to_use=engine_to_use)
        columns = validate_and_expand_columns(columns, ReceiptAPI)  # type: ignore
        extraction = partial(extract_fields, columns=columns)
        data = map(lambda tx: extraction(tx), txns)
        return pd.DataFrame(columns=columns, data=data)

    def __iter__(self) -> Iterator[ReceiptAPI]:  # type: ignore[override]
        yield from self.outgoing

    def __len__(self) -> int:
        """
        The transaction count of the address.
        """

        return self.provider.get_nonce(self.address)

    @singledispatchmethod
    def __getitem__(self, index):
        raise IndexError(f"Can't handle type {type(index)}")

    @__getitem__.register
    def __getitem_int(self, index: int) -> ReceiptAPI:
        if index < 0:
            index += len(self)

        try:
            return cast(
                ReceiptAPI,
                next(
                    self.query_manager.query(
                        AccountTransactionQuery(
                            columns=list(ReceiptAPI.model_fields),
                            account=self.address,
                            start_nonce=index,
                            stop_nonce=index,
                        )
                    )
                ),
            )
        except StopIteration as e:
            raise IndexError(f"index {index} out of range") from e

    @__getitem__.register
    def __getitem_slice(self, indices: slice) -> list[ReceiptAPI]:
        start, stop, step = (
            indices.start or 0,
            indices.stop or len(self),
            indices.step or 1,
        )

        if start < 0:
            start += len(self)

        if stop < 0:
            stop += len(self)

        elif stop > len(self):
            raise ChainError(
                f"'stop={stop}' cannot be greater than account's current nonce ({len(self)})."
            )

        if stop <= start:
            return []  # nothing to query

        return cast(
            list[ReceiptAPI],
            list(
                self.query_manager.query(
                    AccountTransactionQuery(
                        columns=list(ReceiptAPI.model_fields),
                        account=self.address,
                        start_nonce=start,
                        stop_nonce=stop - 1,
                        step=step,
                    )
                )
            ),
        )

    def append(self, receipt: ReceiptAPI):
        """
        Add a receipt to the sessional cache.

        Args:
            receipt (:class:`~ape.api.transactions.ReceiptAPI`): The receipt to append.
        """

        if receipt.txn_hash not in [x.txn_hash for x in self.sessional]:
            self.sessional.append(receipt)

    def revert_to_block(self, block_number: int):
        """
        Remove all receipts after the given block number.

        Args:
            block_number (int): The block number to revert to.
        """

        self.sessional = [x for x in self.sessional if x.block_number <= block_number]


class TransactionHistory(BaseManager):
    """
    A container mapping Transaction History to the transaction from the active session.
    """

    _account_history_cache: dict[AddressType, AccountHistory] = {}
    _hash_to_receipt_map: dict[str, ReceiptAPI] = {}

    @singledispatchmethod
    def __getitem__(self, key):
        raise NotImplementedError(f"Cannot use type of {type(key)} as Index")

    @__getitem__.register
    def __getitem_base_address(self, address: BaseAddress) -> AccountHistory:
        return self._get_account_history(address)

    @__getitem__.register
    def __getitem_str(self, account_or_hash: str) -> Union[AccountHistory, ReceiptAPI]:
        """
        Get a receipt from the history by its transaction hash.
        If the receipt is not currently cached, will use the provider
        to retrieve it.

        Args:
            account_or_hash (str): The hash of the transaction.

        Returns:
            :class:`~ape.api.transactions.ReceiptAPI`: The receipt.
        """

        def _get_receipt() -> Optional[ReceiptAPI]:
            try:
                return self._get_receipt(account_or_hash)
            except Exception:
                return None

        is_account = False
        if not account_or_hash.startswith("0x"):
            # Attempt converting.
            try:
                account_or_hash = self.conversion_manager.convert(account_or_hash, AddressType)
            except Exception:
                # Pretend this never happened.
                pass
            else:
                is_account = True

        try:
            address = self.provider.network.ecosystem.decode_address(account_or_hash)
            history = self._get_account_history(address)
            if len(history) > 0:
                return history

        except Exception as err:
            msg = f"'{account_or_hash}' is not a known address or transaction hash."
            if is_account:
                raise ChainError(msg) from err

            # Try to treat as transaction hash.
            elif receipt := _get_receipt():
                return receipt

            # Not an account or tx hash (with success).
            raise ChainError(msg) from err

        # No account history found. Check for transaction hash.
        if receipt := _get_receipt():
            return receipt

        # Nothing found. Return empty history
        return history

    def _get_receipt(self, txn_hash: str) -> ReceiptAPI:
        if cached_receipt := self._hash_to_receipt_map.get(txn_hash):
            return cached_receipt

        receipt = self.provider.get_receipt(txn_hash, timeout=0)
        self.append(receipt)
        return receipt

    def append(self, txn_receipt: ReceiptAPI):
        """
        Add a transaction to the cache This is useful for sessional-transactions.

        Raises:
            :class:`~ape.exceptions.ChainError`: When trying to append a transaction
              receipt that is already in the list.

        Args:
            txn_receipt (:class:`~ape.api.transactions.ReceiptAPI`): The transaction receipt.
        """

        self._hash_to_receipt_map[txn_receipt.txn_hash] = txn_receipt
        address = self.conversion_manager.convert(txn_receipt.sender, AddressType)
        if address not in self._account_history_cache:
            self._account_history_cache[address] = AccountHistory(address=address)

        self._account_history_cache[address].append(txn_receipt)

    def revert_to_block(self, block_number: int):
        """
        Remove all receipts past the given block number.

        Args:
            block_number (int): The block number to revert to.
        """

        self._hash_to_receipt_map = {
            h: r for h, r in self._hash_to_receipt_map.items() if r.block_number <= block_number
        }
        for account_history in self._account_history_cache.values():
            account_history.revert_to_block(block_number)

    def _get_account_history(self, address: Union[BaseAddress, AddressType]) -> AccountHistory:
        address_key: AddressType = self.conversion_manager.convert(address, AddressType)

        if address_key not in self._account_history_cache:
            self._account_history_cache[address_key] = AccountHistory(address=address_key)

        return self._account_history_cache[address_key]


class ContractCache(BaseManager):
    """
    A collection of cached contracts. Contracts can be cached in two ways:

    1. An in-memory cache of locally deployed contracts
    2. A cache of contracts per network (only permanent networks are stored this way)

    When retrieving a contract, if a :class:`~ape.api.explorers.ExplorerAPI` is used,
    it will be cached to disk for faster look-up next time.
    """

    _local_contract_types: dict[AddressType, ContractType] = {}
    _local_proxies: dict[AddressType, ProxyInfoAPI] = {}
    _local_blueprints: dict[str, ContractType] = {}
    _local_deployments_mapping: dict[str, dict] = {}
    _local_contract_creation: dict[str, ContractCreation] = {}

    # chain_id -> address -> custom_err
    # Cached to prevent calling `new_class` multiple times with conflicts.
    _custom_error_types: dict[int, dict[AddressType, set[type[CustomError]]]] = {}

    @property
    def _network(self) -> NetworkAPI:
        return self.provider.network

    @property
    def _ecosystem_name(self) -> str:
        return self._network.ecosystem.name

    @property
    def _is_live_network(self) -> bool:
        if not self.network_manager.active_provider:
            return False

        return not self._network.is_dev

    @property
    def _data_network_name(self) -> str:
        return self._network.name.replace("-fork", "")

    @property
    def _network_cache(self) -> Path:
        return self._network.ecosystem.data_folder / self._data_network_name

    @property
    def _contract_types_cache(self) -> Path:
        return self._network_cache / "contract_types"

    @property
    def _deployments_mapping_cache(self) -> Path:
        return self._network.ecosystem.data_folder / "deployments_map.json"

    @property
    def _proxy_info_cache(self) -> Path:
        return self._network_cache / "proxy_info"

    @property
    def _blueprint_cache(self) -> Path:
        return self._network_cache / "blueprints"

    @property
    def _contract_creation_cache(self) -> Path:
        return self._network_cache / "contract_creation"

    @property
    def _full_deployments(self) -> dict:
        deployments = self._local_deployments_mapping
        if self._is_live_network:
            deployments = {**deployments, **self._load_deployments_cache()}

        return deployments

    @property
    def _deployments(self) -> dict:
        if not self.network_manager.active_provider:
            return {}

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

        if self.network_manager.active_provider:
            address = self.provider.network.ecosystem.decode_address(int(address, 16))
        else:
            logger.warning("Not connected to a provider. Assuming Ethereum-style checksums.")
            ethereum = self.network_manager.ethereum
            address = ethereum.decode_address(int(address, 16))

        self._cache_contract_type(address, contract_type)

        # NOTE: The txn_hash is not included when caching this way.
        if contract_type.name:
            self._cache_deployment(address, contract_type)

    def __delitem__(self, address: AddressType):
        """
        Delete a cached contract.
        If using a live network, it will also delete the file-cache for the contract.

        Args:
            address (AddressType): The address to remove from the cache.
        """

        if address in self._local_contract_types:
            del self._local_contract_types[address]

        # Delete proxy.
        if address in self._local_proxies:
            info = self._local_proxies[address]
            target = info.target
            del self._local_proxies[address]

            # Also delete target.
            if target in self._local_contract_types:
                del self._local_contract_types[target]

        if self._is_live_network:
            if self._contract_types_cache.is_dir():
                address_file = self._contract_types_cache / f"{address}.json"
                address_file.unlink(missing_ok=True)

            if self._proxy_info_cache.is_dir():
                disk_info = self._get_proxy_info_from_disk(address)
                if disk_info:
                    target = disk_info.target
                    address_file = self._proxy_info_cache / f"{address}.json"
                    address_file.unlink()

                    # Also delete the target.
                    self.__delitem__(target)

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
        contract_type = contract_instance.contract_type

        # Cache contract type in memory before proxy check,
        # in case it is needed somewhere. It may get overridden.
        self._local_contract_types[address] = contract_type

        proxy_info = self.provider.network.ecosystem.get_proxy_info(address)
        if proxy_info:
            self.cache_proxy_info(address, proxy_info)
            contract_type = self.get(proxy_info.target) or contract_type
            if contract_type:
                self._cache_contract_type(address, contract_type)

            return

        txn_hash = contract_instance.txn_hash
        self._cache_contract_type(address, contract_type)
        if contract_type.name:
            self._cache_deployment(address, contract_type, txn_hash)

    def cache_proxy_info(self, address: AddressType, proxy_info: ProxyInfoAPI):
        """
        Cache proxy info for a particular address, useful for plugins adding already
        deployed proxies. When you deploy a proxy locally, it will also call this method.

        Args:
            address (AddressType): The address of the proxy contract.
            proxy_info (:class:`~ape.api.networks.ProxyInfo`): The proxy info class
              to cache.
        """
        if self.get_proxy_info(address) and self._is_live_network:
            return

        self._local_proxies[address] = proxy_info

        if self._is_live_network:
            self._cache_proxy_info_to_disk(address, proxy_info)

    def cache_blueprint(self, blueprint_id: str, contract_type: ContractType):
        """
        Cache a contract blueprint.

        Args:
            blueprint_id (``str``): The ID of the blueprint. For example, in EIP-5202,
              it would be the address of the deployed blueprint. For Starknet, it would
              be the class identifier.
            contract_type (``ContractType``): The contract type associated with the blueprint.
        """

        if self.get_blueprint(blueprint_id) and self._is_live_network:
            return

        self._local_blueprints[blueprint_id] = contract_type

        if self._is_live_network:
            self._cache_blueprint_to_disk(blueprint_id, contract_type)

    def get_proxy_info(self, address: AddressType) -> Optional[ProxyInfoAPI]:
        """
        Get proxy information about a contract using its address,
        either from a local cache, a disk cache, or the provider.

        Args:
            address (AddressType): The address of the proxy contract.

        Returns:
            Optional[:class:`~ape.api.networks.ProxyInfoAPI`]
        """
        return self._local_proxies.get(address) or self._get_proxy_info_from_disk(address)

    def get_creation_metadata(self, address: AddressType) -> Optional[ContractCreation]:
        """
        Get contract creation metadata containing txn_hash, deployer, factory, block.

        Args:
            address (AddressType): The address of the contract.

        Returns:
            Optional[:class:`~ape.api.query.ContractCreation`]
        """
        if creation := self._local_contract_creation.get(address):
            return creation

        # read from disk
        elif creation := self._get_contract_creation_from_disk(address):
            self._local_contract_creation[address] = creation
            return creation

        # query and cache
        query = ContractCreationQuery(columns=["*"], contract=address)
        get_creation = self.query_manager.query(query)

        try:
            if not (creation := next(get_creation, None)):  # type: ignore[arg-type]
                return None

        except QueryEngineError:
            return None

        if self._is_live_network:
            self._cache_contract_creation_to_disk(address, creation)

        self._local_contract_creation[address] = creation
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

        return self._local_blueprints.get(blueprint_id) or self._get_blueprint_from_disk(
            blueprint_id
        )

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
        contract_deployments = deployments.get(contract_type.name or "", [])
        new_deployment = {"address": address, "transaction_hash": txn_hash}
        contract_deployments.append(new_deployment)
        self._deployments = {**deployments, contract_type.name: contract_deployments}

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

        try:
            address_key: AddressType = self.conversion_manager.convert(address, AddressType)
        except ConversionError:
            if not address.startswith("0x"):
                # Still raise conversion errors for ENS and such.
                raise

            # In this case, it at least _looked_ like an address.
            return None

        if contract_type := self._local_contract_types.get(address_key):
            if default and default != contract_type:
                # Replacing contract type
                self._local_contract_types[address_key] = default
                return default

            return contract_type

        if self._network.is_local:
            # Don't check disk-cache or explorer when using local
            if default:
                self._local_contract_types[address_key] = default

            return default

        if not (contract_type := self._get_contract_type_from_disk(address_key)):
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
                return self.get(proxy_info.target, default=default)

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
        txn_hash: Optional[Union[str, HexBytes]] = None,
        abi: Optional[Union[list[ABI], dict, str, Path]] = None,
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

        Returns:
            :class:`~ape.contracts.base.ContractInstance`
        """

        if self.conversion_manager.is_type(address, AddressType):
            contract_address = cast(AddressType, address)
        else:
            try:
                contract_address = self.conversion_manager.convert(address, AddressType)
            except ConversionError as err:
                raise ValueError(f"Unknown address value '{address}'.") from err

        try:
            # Always attempt to get an existing contract type to update caches
            contract_type = self.get(contract_address, default=contract_type)
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

        elif not isinstance(contract_type, ContractType):
            raise TypeError(
                f"Expected type '{ContractType.__name__}' for argument 'contract_type'."
            )

        if not txn_hash:
            # Check for txn_hash in deployments.
            deployments = self._deployments.get(contract_type.name) or []
            for deployment in deployments[::-1]:
                if deployment["address"] == contract_address and "transaction_hash" in deployment:
                    txn_hash = deployment["transaction_hash"]
                    break

        return ContractInstance(contract_address, contract_type, txn_hash=txn_hash)

    def instance_from_receipt(
        self, receipt: ReceiptAPI, contract_type: ContractType
    ) -> ContractInstance:
        """
        A convenience method for creating instances from receipts.

        Args:
            receipt (:class:`~ape.api.transactions.ReceiptAPI`): The receipt.

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
        contract_name = contract_type.name
        if not contract_name:
            return []

        config_deployments = []
        if self.network_manager.active_provider:
            ecosystem_name = self.provider.network.ecosystem.name
            network_name = self.provider.network.name
            all_config_deployments = (
                self.config_manager.deployments if self.config_manager.deployments else {}
            )
            ecosystem_deployments = all_config_deployments.get(ecosystem_name, {})
            network_deployments = ecosystem_deployments.get(network_name, {})
            config_deployments = [
                c for c in network_deployments if c["contract_type"] == contract_name
            ]

        deployments = [*config_deployments, *self._deployments.get(contract_name, [])]
        if not deployments:
            return []

        instances: list[ContractInstance] = []
        for deployment in deployments:
            address = deployment["address"]
            txn_hash = deployment.get("transaction_hash")
            instance = ContractInstance(address, contract_type, txn_hash=txn_hash)
            instances.append(instance)

        return instances

    def clear_local_caches(self):
        """
        Reset local caches to a blank state.
        """
        self._local_contract_types = {}
        self._local_proxies = {}
        self._local_blueprints = {}
        self._local_deployments_mapping = {}
        self._local_contract_creation = {}

    def _get_contract_type_from_disk(self, address: AddressType) -> Optional[ContractType]:
        address_file = self._contract_types_cache / f"{address}.json"
        if not address_file.is_file():
            return None

        return ContractType.model_validate_json(address_file.read_text())

    def _get_proxy_info_from_disk(self, address: AddressType) -> Optional[ProxyInfoAPI]:
        address_file = self._proxy_info_cache / f"{address}.json"
        if not address_file.is_file():
            return None

        return ProxyInfoAPI.model_validate_json(address_file.read_text())

    def _get_blueprint_from_disk(self, blueprint_id: str) -> Optional[ContractType]:
        contract_file = self._blueprint_cache / f"{blueprint_id}.json"
        if not contract_file.is_file():
            return None

        return ContractType.model_validate_json(contract_file.read_text())

    def _get_contract_type_from_explorer(self, address: AddressType) -> Optional[ContractType]:
        if not self._network.explorer:
            return None

        try:
            contract_type = self._network.explorer.get_contract_type(address)
        except Exception as err:
            explorer_name = self._network.explorer.name
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
            self._cache_contract_to_disk(address, contract_type)

        return contract_type

    def _get_contract_creation_from_disk(self, address: AddressType) -> Optional[ContractCreation]:
        path = self._contract_creation_cache / f"{address}.json"
        if not path.is_file():
            return None

        return ContractCreation.model_validate_json(path.read_text())

    def _cache_contract_to_disk(self, address: AddressType, contract_type: ContractType):
        self._contract_types_cache.mkdir(exist_ok=True, parents=True)
        address_file = self._contract_types_cache / f"{address}.json"
        address_file.write_text(contract_type.model_dump_json(), encoding="utf8")

    def _cache_proxy_info_to_disk(self, address: AddressType, proxy_info: ProxyInfoAPI):
        self._proxy_info_cache.mkdir(exist_ok=True, parents=True)
        address_file = self._proxy_info_cache / f"{address}.json"
        address_file.write_text(proxy_info.model_dump_json(), encoding="utf8")

    def _cache_blueprint_to_disk(self, blueprint_id: str, contract_type: ContractType):
        self._blueprint_cache.mkdir(exist_ok=True, parents=True)
        blueprint_file = self._blueprint_cache / f"{blueprint_id}.json"
        blueprint_file.write_text(contract_type.model_dump_json(), encoding="utf8")

    def _cache_contract_creation_to_disk(self, address: AddressType, creation: ContractCreation):
        self._contract_creation_cache.mkdir(exist_ok=True, parents=True)
        path = self._contract_creation_cache / f"{address}.json"
        path.write_text(creation.model_dump_json(), encoding="utf8")

    def _load_deployments_cache(self) -> dict:
        return (
            json.loads(self._deployments_mapping_cache.read_text(encoding="utf8"))
            if self._deployments_mapping_cache.is_file()
            else {}
        )

    def _write_deployments_mapping(self, deployments_map: dict):
        self._deployments_mapping_cache.parent.mkdir(exist_ok=True, parents=True)
        with self._deployments_mapping_cache.open("w") as fp:
            json.dump(deployments_map, fp, sort_keys=True, indent=2, default=sorted)


class ReportManager(BaseManager):
    """
    A class representing the active Ape session. Useful for tracking data and
    building reports.

    **NOTE**: This class is not part of the public API.
    """

    def show_gas(self, report: GasReport, file: Optional[IO[str]] = None):
        tables: list[Table] = []

        for contract_id, method_calls in report.items():
            title = f"{contract_id} Gas"
            table = Table(title=title, box=SIMPLE)
            table.add_column("Method")
            table.add_column("Times called", justify="right")
            table.add_column("Min.", justify="right")
            table.add_column("Max.", justify="right")
            table.add_column("Mean", justify="right")
            table.add_column("Median", justify="right")
            has_at_least_1_row = False

            for method_call, gases in sorted(method_calls.items()):
                if not gases:
                    continue

                if not method_call or is_zero_hex(method_call) or is_evm_precompile(method_call):
                    continue

                elif method_call == "__new__":
                    # Looks better in the gas report.
                    method_call = "__init__"

                has_at_least_1_row = True
                table.add_row(
                    method_call,
                    f"{len(gases)}",
                    f"{min(gases)}",
                    f"{max(gases)}",
                    f"{int(round(mean(gases)))}",
                    f"{int(round(median(gases)))}",
                )

            if has_at_least_1_row:
                tables.append(table)

        self.echo(*tables, file=file)

    def echo(
        self, *rich_items, file: Optional[IO[str]] = None, console: Optional[RichConsole] = None
    ):
        console = console or get_rich_console(file)
        console.print(*rich_items)

    def show_source_traceback(
        self,
        traceback: SourceTraceback,
        file: Optional[IO[str]] = None,
        console: Optional[RichConsole] = None,
        failing: bool = True,
    ):
        console = console or get_rich_console(file)
        style = "red" if failing else None
        console.print(str(traceback), style=style)

    def show_events(
        self, events: list, file: Optional[IO[str]] = None, console: Optional[RichConsole] = None
    ):
        console = console or get_rich_console(file)
        console.print("Events emitted:")
        for event in events:
            console.print(event)

    def _get_console(self, *args, **kwargs):
        # TODO: Delete this method in v0.9.
        # It only exists for backwards compat.
        return get_rich_console(*args, **kwargs)


class ChainManager(BaseManager):
    """
    A class for managing the state of the active blockchain.
    Also handy for querying data about the chain and managing local caches.
    Access the chain manager singleton from the root ``ape`` namespace.

    Usage example::

        from ape import chain
    """

    _snapshots: defaultdict = defaultdict(list)  # chain_id -> snapshots
    _chain_id_map: dict[str, int] = {}
    _block_container_map: dict[int, BlockContainer] = {}
    _transaction_history_map: dict[int, TransactionHistory] = {}
    contracts: ContractCache = ContractCache()
    _reports: ReportManager = ReportManager()

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
    def history(self) -> TransactionHistory:
        """
        A mapping of transactions from the active session to the account responsible.
        """
        try:
            chain_id = self.chain_id
        except ProviderNotConnectedError:
            return TransactionHistory()  # Empty list.

        if chain_id not in self._transaction_history_map:
            history = TransactionHistory()
            self._transaction_history_map[chain_id] = history

        return self._transaction_history_map[chain_id]

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
        self.provider.set_timestamp(self.conversion_manager.convert(new_value, int))

    @log_instead_of_fail(default="<ChainManager>")
    def __repr__(self) -> str:
        props = f"id={self.chain_id}" if self.network_manager.active_provider else "disconnected"
        cls_name = getattr(type(self), "__name__", ChainManager.__name__)
        return f"<{cls_name} ({props})>"

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
        chain_id = self.provider.chain_id
        snapshot_id = self.provider.snapshot()
        if snapshot_id not in self._snapshots[chain_id]:
            self._snapshots[chain_id].append(snapshot_id)

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
        chain_id = self.provider.chain_id
        if snapshot_id is None and not self._snapshots[chain_id]:
            raise ChainError("There are no snapshots to revert to.")
        elif snapshot_id is None:
            snapshot_id = self._snapshots[chain_id].pop()
        elif snapshot_id not in self._snapshots[chain_id]:
            raise UnknownSnapshotError(snapshot_id)
        else:
            snapshot_index = self._snapshots[chain_id].index(snapshot_id)
            self._snapshots[chain_id] = self._snapshots[chain_id][:snapshot_index]

        self.provider.restore(snapshot_id)
        self.history.revert_to_block(self.blocks.height)

    @contextmanager
    def isolate(self):
        """
        Run code in an isolated context.
        Requires using a local provider that supports snapshotting.

        Usages example::

            owner = accounts[0]
            with chain.isolate():
                contract = owner.deploy(project.MyContract)
                receipt = contract.fooBar(sender=owner)
        """

        snapshot = None
        try:
            snapshot = self.snapshot()
        except APINotImplementedError:
            logger.warning("Provider does not support snapshotting.")
        pending = self.pending_timestamp

        start_ecosystem_name = self.provider.network.ecosystem.name
        start_network_name = self.provider.network.name
        start_provider_name = self.provider.name

        try:
            yield
        finally:
            if snapshot is None:
                logger.error("Failed to create snapshot.")
                return

            end_ecosystem_name = self.provider.network.ecosystem.name
            end_network_name = self.provider.network.name
            end_provider_name = self.provider.name

            if (
                start_ecosystem_name != end_ecosystem_name
                or start_network_name != end_network_name
                or start_provider_name != end_provider_name
            ):
                logger.warning("Provider changed before isolation completed.")
                return

            self.chain_manager.restore(snapshot)

            try:
                self.pending_timestamp = pending
            except APINotImplementedError:
                # Provider does not support time travel.
                pass

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
                Defaults to None.
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
            account = account.address

        if isinstance(amount, str) and len(str(amount).split(" ")) > 1:
            # Support values like "1000 ETH".
            amount = self.conversion_manager.convert(amount, int)
        elif isinstance(amount, str):
            # Support hex strings
            amount = int(amount, 16)

        return self.provider.set_balance(account, amount)

    def get_receipt(self, transaction_hash: str) -> ReceiptAPI:
        """
        Get a transaction receipt from the chain.

        Args:
            transaction_hash (str): The hash of the transaction.

        Returns:
            :class:`~ape.apt.transactions.ReceiptAPI`
        """
        receipt = self.chain_manager.history[transaction_hash]
        if not isinstance(receipt, ReceiptAPI):
            raise TransactionNotFoundError(transaction_hash=transaction_hash)

        return receipt
