import pytest

from ape import api
from ape.api import providers


@pytest.mark.parametrize(
    "name",
    [
        "BlockAPI",
        "ProviderAPI",
        "SubprocessProvider",
        "TestProviderAPI",
        "UpstreamProvider",
    ],
)
def test_provider_exports_are_lazy_loaded(name):
    assert getattr(api, name) is getattr(providers, name)
