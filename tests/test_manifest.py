import pytest  # type: ignore
import requests
from hypothesis import HealthCheck, given, settings  # type: ignore
from hypothesis_jsonschema import from_schema  # type: ignore

from ape.types.manifest import PackageManifest

ETHPM_MANIFEST_SCHEMA_URI = (
    "https://raw.githubusercontent.com/ethpm/ethpm-spec/master/spec/v3.spec.json"
)


@pytest.mark.xfail(reason="Schema is poorly formed")
@pytest.mark.fuzzing
@given(manifest_dict=from_schema(requests.get(ETHPM_MANIFEST_SCHEMA_URI).json()))
@settings(suppress_health_check=(HealthCheck.too_slow,))
def test_manifest_parsing(manifest_dict):
    manifest = PackageManifest.from_dict(manifest_dict)
    assert manifest.to_dict() == manifest_dict


@pytest.mark.parametrize(
    "example",
    [
        # From https://github.com/ethpm/ethpm-spec/tree/master/examples
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
def test_example_manifests(example):
    # NOTE: `v3-pretty.json` exists for each, and can be used for debugging
    manifest_uri = (
        f"https://raw.githubusercontent.com/ethpm/ethpm-spec/master/examples/{example}/v3.json"
    )
    manifest_dict = requests.get(manifest_uri).json()
    manifest = PackageManifest.from_dict(manifest_dict)
    assert manifest.to_dict() == manifest_dict
