from typing import Iterator, List

import pytest

from ape.api import TestAccountAPI
from ape.managers.chain import ChainManager
from ape.managers.project import ProjectManager
from ape.utils import ManagerAccessMixin


class PytestApeFixtures(ManagerAccessMixin):
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
        snapshot_id = self.chain_manager.snapshot()
        yield
        if snapshot_id in self.chain_manager._snapshots:
            self.chain_manager.restore(snapshot_id)

    @pytest.fixture(scope="package")
    def _package_isolation(self, _session_isolation) -> Iterator[None]:
        snapshot_id = self.chain_manager.snapshot()
        yield
        if snapshot_id in self.chain_manager._snapshots:
            self.chain_manager.restore(snapshot_id)

    @pytest.fixture(scope="module")
    def _module_isolation(self, _package_isolation) -> Iterator[None]:
        snapshot_id = self.chain_manager.snapshot()
        yield
        if snapshot_id in self.chain_manager._snapshots:
            self.chain_manager.restore(snapshot_id)

    @pytest.fixture(scope="class")
    def _class_isolation(self, _module_isolation) -> Iterator[None]:
        snapshot_id = self.chain_manager.snapshot()
        yield
        if snapshot_id in self.chain_manager._snapshots:
            self.chain_manager.restore(snapshot_id)

    @pytest.fixture(scope="function")
    def _function_isolation(self, _class_isolation) -> Iterator[None]:
        snapshot_id = self.chain_manager.snapshot()
        yield
        if snapshot_id in self.chain_manager._snapshots:
            self.chain_manager.restore(snapshot_id)
