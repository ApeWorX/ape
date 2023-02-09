import copy
from fnmatch import fnmatch
from typing import Dict, Iterator, List, Optional

import pytest

from ape.api import ReceiptAPI, TestAccountAPI
from ape.logging import logger
from ape.managers.chain import ChainManager
from ape.managers.networks import NetworkManager
from ape.managers.project import ProjectManager
from ape.pytest.config import ConfigWrapper
from ape.types import SnapshotID
from ape.utils import ManagerAccessMixin, allow_disconnected, cached_property


class PytestApeFixtures(ManagerAccessMixin):
    # NOTE: Avoid including links, markdown, or rst in method-docs
    # for fixtures, as they are used in output from the command
    # `ape test -q --fixture` (`pytest -q --fixture`).

    _warned_for_unimplemented_snapshot = False
    receipt_capture: "ReceiptCapture"

    def __init__(self, config_wrapper: ConfigWrapper, receipt_capture: "ReceiptCapture"):
        self.config_wrapper = config_wrapper
        self.receipt_capture = receipt_capture

    @cached_property
    def _using_traces(self) -> bool:
        return (
            self.network_manager.provider is not None
            and self.provider.is_connected
            and self.provider.supports_tracing
            # Has reason to use traces?
            and self.config_wrapper.track_gas
        )

    @pytest.fixture(scope="session")
    def accounts(self) -> List[TestAccountAPI]:
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

        return self.project_manager

    def _isolation(self) -> Iterator[None]:
        """
        Isolation logic used to implement isolation fixtures for each pytest scope.
        When tracing support is available, will also assist in capturing receipts.
        """

        snapshot_id = self._snapshot()

        if self._using_traces:
            with self.receipt_capture:
                yield
        else:
            yield

        if snapshot_id:
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
            if not self._warned_for_unimplemented_snapshot:
                logger.warning(
                    "The connected provider does not support snapshotting. "
                    "Tests will not be completely isolated."
                )
                self._warned_for_unimplemented_snapshot = True

        return None

    @allow_disconnected
    def _restore(self, snapshot_id: SnapshotID):
        if snapshot_id not in self.chain_manager._snapshots:
            return

        self.chain_manager.restore(snapshot_id)


class ReceiptCapture(ManagerAccessMixin):
    config_wrapper: ConfigWrapper
    receipt_map: Dict[str, Dict[str, ReceiptAPI]] = {}
    enter_blocks: List[int] = []

    def __init__(self, config_wrapper: ConfigWrapper):
        self.config_wrapper = config_wrapper
        self.chain_manager._reports.track_gas = self.config_wrapper.track_gas
        self.chain_manager._reports.gas_exclusions = self.config_wrapper.gas_exclusions

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
        transactions = [t for b in blocks for t in b.transactions if t.receiver and t.sender]

        for txn in transactions:
            self.capture(txn.txn_hash.hex())

    def capture(self, transaction_hash: str):
        receipt = self.chain_manager.history[transaction_hash]
        if not receipt:
            return

        contract_address = receipt.receiver
        if not contract_address:
            # TODO: Handle deploy receipts once trace supports it
            return

        contract_type = self.chain_manager.contracts.get(contract_address)
        if not contract_type:
            # Not an invoke-transaction or a known address
            return

        source_id = contract_type.source_id or None
        if not source_id:
            # Not a local or known contract type.
            return

        elif source_id not in self.receipt_map:
            self.receipt_map[source_id] = {}

        if transaction_hash in self.receipt_map[source_id]:
            # Transaction already known.
            return

        self.receipt_map[source_id][transaction_hash] = receipt
        if not self.config_wrapper.track_gas:
            # Only capture trace if has a reason to.
            return

        receipt.track_gas()

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


def _build_report(report: Dict, contract: str, method: str, usages: List) -> Dict:
    new_dict = copy.deepcopy(report)
    if contract not in new_dict:
        new_dict[contract] = {method: usages}
    elif method not in new_dict[contract]:
        new_dict[contract][method] = usages
    else:
        new_dict[contract][method].extend(usages)

    return new_dict
