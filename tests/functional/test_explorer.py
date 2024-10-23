from typing import Optional

import pytest
from ethpm_types import ContractType

from ape.api.explorers import ExplorerAPI
from ape.types.address import AddressType


class MyExplorer(ExplorerAPI):
    def get_transaction_url(self, transaction_hash: str) -> str:
        return ""

    def get_address_url(self, address: AddressType) -> str:
        return ""

    def get_contract_type(self, address: AddressType) -> Optional[ContractType]:
        return None

    def publish_contract(self, address: AddressType):
        return


@pytest.fixture
def explorer(networks):
    return MyExplorer(name="mine", network=networks.ethereum.local)


def test_supports_chain(explorer):
    assert not explorer.supports_chain(1)
