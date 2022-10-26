from typing import Dict, Iterator, List, Optional

import pytest
from _pytest.config import Config as PytestConfig
from evm_trace.gas import merge_reports

from ape.api import ReceiptAPI, TestAccountAPI
from ape.logging import logger
from ape.managers.chain import ChainManager
from ape.managers.networks import NetworkManager
from ape.managers.project import ProjectManager
from ape.types import GasReport, SnapshotID
from ape.utils import CallTraceParser, ManagerAccessMixin, allow_disconnected, cached_property


class PytestApeFixtures(ManagerAccessMixin):
    # NOTE: Avoid including links, markdown, or rst in method-docs
    # for fixtures, as they are used in output from the command
    # `ape test -q --fixture` (`pytest -q --fixture`).

    _warned_for_unimplemented_snapshot = False
    pytest_config: PytestConfig
    receipt_capture: "ReceiptCapture"

    def __init__(self, pytest_config, receipt_capture: "ReceiptCapture"):
        self.pytest_config = pytest_config
        self.receipt_capture = receipt_capture

    @cached_property
    def _using_traces(self) -> bool:
        return (
            self.network_manager.provider is not None
            and self.provider.is_connected
            and self.provider.supports_tracing
        )

    @pytest.fixture(scope="session")
    def accounts(self) -> List[TestAccountAPI]:
        """
        A collection of pre-funded accounts.
        """

        return self.account_manager.test_accounts

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
    pytest_config: PytestConfig
    gas_report: Optional[GasReport] = None
    receipt_map: Dict[str, ReceiptAPI] = {}
    enter_blocks: List[int] = []

    def __init__(self, pytest_config):
        self.pytest_config = pytest_config

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

    @cached_property
    def _track_gas(self) -> bool:
        return self.pytest_config.getoption("--gas")

    def capture_range(self, start_block: int, stop_block: int):
        blocks = self.chain_manager.blocks.range(start_block, stop_block + 1)
        transactions = [
            t
            for b in blocks
            for t in b.transactions
            if t.receiver and t.sender and t.sender in self.chain_manager.account_history
        ]

        for txn in transactions:
            self.capture(txn.txn_hash.hex())

    def capture(self, transaction_hash: str, track_gas: Optional[bool] = None):
        if transaction_hash in self.receipt_map:
            return

        receipt = self.chain_manager.account_history.get_receipt(transaction_hash)
        self.receipt_map[transaction_hash] = receipt
        if not receipt:
            return

        if not receipt.receiver:
            # TODO: Handle deploy receipts once trace supports it
            return

        # Merge-in the receipt's gas report with everything so far.
        call_tree = receipt.call_tree
        do_track_gas = track_gas if track_gas is not None else self._track_gas
        if do_track_gas and call_tree:
            parser = CallTraceParser(receipt)
            gas_report = parser._get_rich_gas_report(call_tree)
            if self.gas_report:
                self.gas_report = merge_reports(self.gas_report, gas_report)
            else:
                self.gas_report = gas_report

    @allow_disconnected
    def _get_block_number(self) -> Optional[int]:
        return self.provider.get_block("latest").number
