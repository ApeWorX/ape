from typing import List

import pytest

from ape.api import ProviderAPI, TestAccountAPI
from ape.managers.accounts import AccountManager
from ape.managers.chain import ChainManager
from ape.managers.networks import NetworkManager
from ape.managers.project import ProjectManager


class PytestApeFixtures:
    def __init__(
        self,
        accounts: AccountManager,
        networks: NetworkManager,
        project: ProjectManager,
        chain: ChainManager,
    ):
        self._accounts = accounts
        self._networks = networks
        self._project = project
        self._chain = chain

    @pytest.fixture
    def accounts(self, provider) -> List[TestAccountAPI]:
        return self._accounts.test_accounts

    @pytest.fixture
    def chain(self) -> ChainManager:
        return self._chain

    @pytest.fixture
    def provider(self) -> ProviderAPI:
        return self._chain.provider

    @pytest.fixture(scope="session")
    def project(self) -> ProjectManager:
        return self._project
