from collections.abc import Iterator
from fnmatch import fnmatch
from functools import cached_property
from typing import Optional

import pytest
from eth_utils import to_hex

from ape.api.accounts import TestAccountAPI
from ape.api.transactions import ReceiptAPI
from ape.exceptions import BlockNotFoundError, ChainError
from ape.logging import logger
from ape.managers.chain import ChainManager
from ape.managers.networks import NetworkManager
from ape.managers.project import ProjectManager
from ape.pytest.config import ConfigWrapper
from ape.types.vm import SnapshotID
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.rpc import allow_disconnected


class PytestApeFixtures(ManagerAccessMixin):
    # NOTE: Avoid including links, markdown, or rst in method-docs
    # for fixtures, as they are used in output from the command
    # `ape test -q --fixture` (`pytest -q --fixture`).

    _supports_snapshot: bool = True
    receipt_capture: "ReceiptCapture"

    def __init__(self, config_wrapper: ConfigWrapper, receipt_capture: "ReceiptCapture"):
        self.config_wrapper = config_wrapper
        self.receipt_capture = receipt_capture

    @cached_property
    def _track_transactions(self) -> bool:
        return (
            self.network_manager.provider is not None
            and self.provider.is_connected
            and (self.config_wrapper.track_gas or self.config_wrapper.track_coverage)
        )

    @pytest.fixture(scope="session")
    def accounts(self) -> list[TestAccountAPI]:
        """
        A collection of pre-funded accounts.
        """
        return self.account_manager.test_accounts

    @pytest.fixture(scope="session")
    def compilers(self):
        """
        Access compiler manager directly.
        """
        return self.compiler_manager

    @pytest.fixture(scope="session")
    def chain(self) -> ChainManager:
        """
        Manipulate the blockchain, such as mine or change the pending timestamp.
        """
        return self.chain_manager

    @pytest.fixture(scope="session")
    def networks(self) -> NetworkManager:
        """
        Connect to other networks in your tests.
        """
        return self.network_manager

    @pytest.fixture(scope="session")
    def project(self) -> ProjectManager:
        """
        Access contract types and dependencies.
        """
        return self.local_project

    @pytest.fixture(scope="session")
    def Contract(self):
        """
        Instantiate a reference to an on-chain contract
        using its address (same as ``ape.Contract``).
        """
        return self.chain_manager.contracts.instance_at

    def _isolation(self) -> Iterator[None]:
        """
        Isolation logic used to implement isolation fixtures for each pytest scope.
        When tracing support is available, will also assist in capturing receipts.
        """
        snapshot_id = None

        if self._supports_snapshot:
            try:
                snapshot_id = self._snapshot()
            except BlockNotFoundError:
                self._supports_snapshot = False

        if self._track_transactions:
            did_yield = False
            try:
                with self.receipt_capture:
                    yield
                    did_yield = True

            except BlockNotFoundError:
                if not did_yield:
                    # Prevent double yielding.
                    yield

        else:
            yield

        if snapshot_id is not None:
            self._restore(snapshot_id)

    # isolation fixtures
    _session_isolation = pytest.fixture(_isolation, scope="session")
    _package_isolation = pytest.fixture(_isolation, scope="package")
    _module_isolation = pytest.fixture(_isolation, scope="module")
    _class_isolation = pytest.fixture(_isolation, scope="class")
    _function_isolation = pytest.fixture(_isolation, scope="function")

    @allow_disconnected
    def _snapshot(self) -> Optional[SnapshotID]:
        try:
            return self.chain_manager.snapshot()
        except NotImplementedError:
            logger.warning(
                "The connected provider does not support snapshotting. "
                "Tests will not be completely isolated."
            )
            # To avoid trying again
            self._supports_snapshot = False

        return None

    @allow_disconnected
    def _restore(self, snapshot_id: SnapshotID):
        if snapshot_id not in self.chain_manager._snapshots[self.provider.chain_id]:
            return
        try:
            self.chain_manager.restore(snapshot_id)
        except NotImplementedError:
            logger.warning(
                "The connected provider does not support snapshotting. "
                "Tests will not be completely isolated."
            )
            # To avoid trying again
            self._supports_snapshot = False


class ReceiptCapture(ManagerAccessMixin):
    config_wrapper: ConfigWrapper
    receipt_map: dict[str, dict[str, ReceiptAPI]] = {}
    enter_blocks: list[int] = []

    def __init__(self, config_wrapper: ConfigWrapper):
        self.config_wrapper = config_wrapper

    def __enter__(self):
        block_number = self._get_block_number()
        if block_number is not None:
            self.enter_blocks.append(block_number)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.enter_blocks:
            return

        start_block = self.enter_blocks.pop()
        stop_block = self._get_block_number()
        if stop_block is None or start_block > stop_block:
            return

        self.capture_range(start_block, stop_block)

    def capture_range(self, start_block: int, stop_block: int):
        blocks = self.chain_manager.blocks.range(start_block, stop_block + 1)
        transactions = [t for b in blocks for t in b.transactions]

        for txn in transactions:
            try:
                txn_hash = to_hex(txn.txn_hash)
            except Exception:
                # Might have been from an impersonated account.
                # Those txns need to be added separately, same as tracing calls.
                # Likely, it was already accounted before this point.
                continue

            self.capture(txn_hash)

    def capture(self, transaction_hash: str):
        try:
            receipt = self.chain_manager.history[transaction_hash]
        except ChainError:
            return

        if not receipt:
            return

        elif not (contract_address := (receipt.receiver or receipt.contract_address)):
            return

        elif not (contract_type := self.chain_manager.contracts.get(contract_address)):
            # Not an invoke-transaction or a known address
            return

        elif not (source_id := (contract_type.source_id or None)):
            # Not a local or known contract type.
            return

        elif source_id not in self.receipt_map:
            self.receipt_map[source_id] = {}

        if transaction_hash in self.receipt_map[source_id]:
            # Transaction already known.
            return

        self.receipt_map[source_id][transaction_hash] = receipt
        if self.config_wrapper.track_gas:
            receipt.track_gas()

        if self.config_wrapper.track_coverage:
            receipt.track_coverage()

    def clear(self):
        self.receipt_map = {}
        self.enter_blocks = []

    @allow_disconnected
    def _get_block_number(self) -> Optional[int]:
        return self.provider.get_block("latest").number

    def _exclude_from_gas_report(
        self, contract_name: str, method_name: Optional[str] = None
    ) -> bool:
        """
        Helper method to determine if a certain contract / method combination should be
        excluded from the gas report.
        """
        for exclusion in self.config_wrapper.gas_exclusions:
            # Default to looking at all contracts
            contract_pattern = exclusion.contract_name
            if not fnmatch(contract_name, contract_pattern) or not method_name:
                continue

            method_pattern = exclusion.method_name
            if not method_pattern or fnmatch(method_name, method_pattern):
                return True

        return False
