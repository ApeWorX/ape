from typing import List

import pytest

from ape.api import TestAccountAPI
from ape.managers.accounts import AccountManager
from ape.managers.chain import ChainManager
from ape.managers.networks import NetworkManager
from ape.managers.project import ProjectManager


class PytestApeFixtures:
    def __init__(
        self,
        account_manager: AccountManager,
        network_manager: NetworkManager,
        project_manager: ProjectManager,
        chain_manager: ChainManager,
    ):
        self.account_manager = account_manager
        self.network_manager = network_manager
        self._project = project_manager
        self.chain_manager = chain_manager

    @pytest.fixture(scope="session")
    def accounts(self) -> List[TestAccountAPI]:
        return self.account_manager.test_accounts

    @pytest.fixture(scope="session")
    def chain(self) -> ChainManager:
        return self.chain_manager

    @pytest.fixture(scope="session")
    def project(self) -> ProjectManager:
        return self._project
