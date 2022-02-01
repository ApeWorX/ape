from typing import List

import pytest

from ape.api import TestAccountAPI
from ape.managers.chain import ChainManager
from ape.managers.project import ProjectManager
from ape.utils import ManagerAccessBase


class PytestApeFixtures(ManagerAccessBase):
    def __init__(
        self,
        project_manager: ProjectManager,
    ):
        self._project = project_manager

    @pytest.fixture(scope="session")
    def accounts(self) -> List[TestAccountAPI]:
        return self.account_manager.test_accounts

    @pytest.fixture(scope="session")
    def chain(self) -> ChainManager:
        return self.chain_manager

    @pytest.fixture(scope="session")
    def project(self) -> ProjectManager:
        return self._project
