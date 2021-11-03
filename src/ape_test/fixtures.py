from typing import List

import pytest

from ape.api import ProviderAPI, TestAccountAPI
from ape.exceptions import ProviderError
from ape.managers.accounts import AccountManager
from ape.managers.networks import NetworkManager
from ape.managers.project import ProjectManager


class PytestApeFixtures:
    def __init__(self, accounts: AccountManager, networks: NetworkManager, project: ProjectManager):
        self._accounts = accounts
        self._networks = networks
        self._project = project

    @pytest.fixture
    def accounts(self, provider) -> List[TestAccountAPI]:
        return self._accounts.test_accounts

    @pytest.fixture
    def provider(self) -> ProviderAPI:
        active_provider = self._networks.active_provider

        if active_provider is None:
            raise ProviderError("Provider is not set.")

        return active_provider

    @pytest.fixture(scope="session")
    def project(self) -> ProjectManager:
        return self._project
