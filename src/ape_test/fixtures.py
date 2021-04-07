import pytest

from ape import accounts


class PytestApeFixtures:
    @pytest.fixture(scope="session")
    def accounts(self):
        """Ape accounts container. Access to all loaded accounts."""
        return accounts

    @pytest.fixture(scope="session")
    def a(self):
        """Short form of the `accounts` fixture."""
        return accounts
