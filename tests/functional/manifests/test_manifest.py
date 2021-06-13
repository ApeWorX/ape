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


def test_example_manifests(manifest):
    assert PackageManifest.from_dict(manifest).to_dict() == manifest
