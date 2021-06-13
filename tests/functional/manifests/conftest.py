import json
from pathlib import Path

import pytest  # type: ignore


@pytest.fixture(
    scope="session",
    params=[
        # Copied from https://github.com/ethpm/ethpm-spec/tree/master/examples
        "escrow",
        "owned",
        "piper-coin",
        "safe-math-lib",
        "standard-token",
        "transferable",
        "wallet-with-send",
        "wallet",
    ],
)
def manifest(request):
    yield json.loads((Path(__file__).parent / "data" / f"{request.param}.json").read_text())
