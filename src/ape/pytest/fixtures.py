from typing import Iterator, List

import pytest

from ape.api import TestAccountAPI
from ape.logging import logger
from ape.managers.chain import ChainManager
from ape.managers.project import ProjectManager
from ape.utils import ManagerAccessMixin


class PytestApeFixtures(ManagerAccessMixin):
    def __init__(self):
        self._warned_for_missing_features = False

    @pytest.fixture(scope="session")
    def accounts(self) -> List[TestAccountAPI]:
        return self.account_manager.test_accounts

    @pytest.fixture(scope="session")
    def chain(self) -> ChainManager:
        return self.chain_manager

    @pytest.fixture(scope="session")
    def project(self) -> ProjectManager:
        return self.project_manager

    @pytest.fixture(scope="session")
    def _session_isolation(self) -> Iterator[None]:
        snapshot_id = None
        try:
            snapshot_id = self.chain_manager.snapshot()
        except NotImplementedError:
            self._warn_for_unimplemented_snapshot()

        yield

        if snapshot_id is not None and snapshot_id in self.chain_manager._snapshots:
            self.chain_manager.restore(snapshot_id)

    @pytest.fixture(scope="package")
    def _package_isolation(self, _session_isolation) -> Iterator[None]:
        snapshot_id = None
        try:
            snapshot_id = self.chain_manager.snapshot()
        except NotImplementedError:
            self._warn_for_unimplemented_snapshot()

        yield

        if snapshot_id is not None and snapshot_id in self.chain_manager._snapshots:
            self.chain_manager.restore(snapshot_id)

    @pytest.fixture(scope="module")
    def _module_isolation(self, _package_isolation) -> Iterator[None]:
        snapshot_id = None
        try:
            snapshot_id = self.chain_manager.snapshot()
        except NotImplementedError:
            self._warn_for_unimplemented_snapshot()

        yield

        if snapshot_id is not None and snapshot_id in self.chain_manager._snapshots:
            self.chain_manager.restore(snapshot_id)

    @pytest.fixture(scope="class")
    def _class_isolation(self, _module_isolation) -> Iterator[None]:
        snapshot_id = None
        try:
            snapshot_id = self.chain_manager.snapshot()
        except NotImplementedError:
            self._warn_for_unimplemented_snapshot()

        yield

        if snapshot_id is not None and snapshot_id in self.chain_manager._snapshots:
            self.chain_manager.restore(snapshot_id)

    @pytest.fixture(scope="function")
    def _function_isolation(self, _class_isolation) -> Iterator[None]:
        snapshot_id = None
        try:
            snapshot_id = self.chain_manager.snapshot()
        except NotImplementedError:
            self._warn_for_unimplemented_snapshot()

        yield

        if snapshot_id is not None and snapshot_id in self.chain_manager._snapshots:
            self.chain_manager.restore(snapshot_id)

    def _warn_for_unimplemented_snapshot(self):
        if self._warned_for_missing_features:
            return

        logger.warning(
            "The connected provider does not support snapshotting. "
            "Tests will not be completely isolated."
        )
        self._warned_for_missing_features = True
