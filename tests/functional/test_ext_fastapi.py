import inspect
from unittest.mock import MagicMock, patch

import pytest

# Skip the entire module if fastapi is not installed.
fastapi = pytest.importorskip("fastapi")

from fastapi import FastAPI, Query  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from ape.ext.fastapi import network_context  # noqa: E402


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_app_and_client(handler):
    app = FastAPI()
    app.get("/test")(handler)
    return TestClient(app, raise_server_exceptions=True)


def _mock_network_ctx():
    ctx = MagicMock()
    ctx.__enter__ = MagicMock(return_value=None)
    ctx.__exit__ = MagicMock(return_value=False)
    return ctx


# ---------------------------------------------------------------------------
# Test 1 — decorator adds ecosystem/network to signature automatically
# ---------------------------------------------------------------------------

class TestSignaturePatch:
    def test_ecosystem_and_network_added_when_not_in_original(self):

        @network_context()
        def handler(token: str) -> dict:
            return {"token": token}

        sig = inspect.signature(handler)
        assert "ecosystem" in sig.parameters
        assert "network" in sig.parameters

    def test_ecosystem_and_network_not_duplicated_when_already_present(self):

        @network_context()
        def handler(token: str, ecosystem: str, network: str) -> dict:
            return {}

        sig = inspect.signature(handler)
        param_names = list(sig.parameters.keys())
        assert param_names.count("ecosystem") == 1
        assert param_names.count("network") == 1

    def test_original_params_preserved_in_signature(self):

        @network_context()
        def handler(token: str, amount: int) -> dict:
            return {}

        sig = inspect.signature(handler)
        assert "token" in sig.parameters
        assert "amount" in sig.parameters


# ---------------------------------------------------------------------------
# Test 2 — network context is entered with the correct choice string
# ---------------------------------------------------------------------------

class TestNetworkContextEntered:
    def test_correct_choice_string_passed_to_parse_network_choice(self):

        mock_ctx = _mock_network_ctx()

        @network_context()
        def handler(token: str) -> dict:
            return {"token": token}

        client = _make_app_and_client(handler)

        with patch("ape.networks") as mock_networks:
            mock_networks.parse_network_choice.return_value = mock_ctx
            client.get("/test?token=USDC&ecosystem=ethereum&network=mainnet")

        mock_networks.parse_network_choice.assert_called_once_with("ethereum:mainnet")

    def test_different_ecosystem_and_network(self):

        mock_ctx = _mock_network_ctx()

        @network_context()
        def handler() -> dict:
            return {}

        client = _make_app_and_client(handler)

        with patch("ape.networks") as mock_networks:
            mock_networks.parse_network_choice.return_value = mock_ctx
            client.get("/test?ecosystem=polygon&network=mainnet")

        mock_networks.parse_network_choice.assert_called_once_with("polygon:mainnet")


# ---------------------------------------------------------------------------
# Test 3 — kwargs passed to original function
# ---------------------------------------------------------------------------

class TestKwargsBehaviour:
    def test_ecosystem_network_stripped_when_not_in_original_signature(self):

        received: dict = {}

        @network_context()
        def handler(token: str) -> dict:
            received.update({"token": token})
            return received

        client = _make_app_and_client(handler)

        with patch("ape.networks") as mock_networks:
            mock_networks.parse_network_choice.return_value = _mock_network_ctx()
            response = client.get("/test?token=USDC&ecosystem=ethereum&network=mainnet")

        assert response.status_code == 200
        assert "ecosystem" not in received
        assert "network" not in received
        assert received["token"] == "USDC"

    def test_ecosystem_network_passed_through_when_in_original_signature(self):

        received: dict = {}

        @network_context()
        def handler(token: str, ecosystem: str, network: str) -> dict:
            received.update({"token": token, "ecosystem": ecosystem, "network": network})
            return received

        client = _make_app_and_client(handler)

        with patch("ape.networks") as mock_networks:
            mock_networks.parse_network_choice.return_value = _mock_network_ctx()
            response = client.get("/test?token=USDC&ecosystem=ethereum&network=mainnet")

        assert response.status_code == 200
        assert received == {"token": "USDC", "ecosystem": "ethereum", "network": "mainnet"}


# ---------------------------------------------------------------------------
# Test 4 — functools.wraps preserves original function metadata
# ---------------------------------------------------------------------------

class TestWrapsMetadata:
    def test_function_name_preserved(self):
        @network_context()
        def my_special_handler() -> dict:
            return {}

        assert my_special_handler.__name__ == "my_special_handler"

    def test_docstring_preserved(self):
        @network_context()
        def handler() -> dict:
            """My docstring."""
            return {}

        assert handler.__doc__ == "My docstring."
