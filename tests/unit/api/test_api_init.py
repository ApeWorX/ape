import pytest

import ape.api as api
import ape.api.providers as providers


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
