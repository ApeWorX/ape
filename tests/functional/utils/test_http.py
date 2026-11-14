import os
from contextlib import contextmanager

import pytest

from ape.api.config import ApeConfig, ProxyConfig
from ape.utils.http import (
    apply_proxy_env,
    get_httpx_client,
    get_proxy_url,
    get_requests_proxies,
)

PROXY_URL = "http://proxy.example.com:8080"
NO_PROXY_HOSTS = ["localhost", "127.0.0.1", "internal-rpc.company.com"]

_PROXY_ENV_KEYS = (
    "HTTP_PROXY",
    "HTTPS_PROXY",
    "ALL_PROXY",
    "NO_PROXY",
    "http_proxy",
    "https_proxy",
    "all_proxy",
    "no_proxy",
)


@contextmanager
def clean_proxy_env():
    """Temporarily remove all proxy-related env vars."""
    saved = {key: os.environ.pop(key) for key in list(_PROXY_ENV_KEYS) if key in os.environ}
    try:
        yield
    finally:
        for key in _PROXY_ENV_KEYS:
            os.environ.pop(key, None)
        os.environ.update(saved)


class TestProxyConfig:
    def test_default(self):
        cfg = ProxyConfig()
        assert cfg.url is None
        assert cfg.no_proxy == []

    def test_parse_from_ape_config(self):
        cfg = ApeConfig.model_validate(
            {
                "proxy": {
                    "url": PROXY_URL,
                    "no_proxy": NO_PROXY_HOSTS,
                }
            }
        )
        assert cfg.proxy.url == PROXY_URL
        assert cfg.proxy.no_proxy == NO_PROXY_HOSTS

    def test_future_per_protocol_extra_allowed(self):
        # Flat schema today; extras reserved for future http/https keys.
        cfg = ProxyConfig.model_validate(
            {"url": PROXY_URL, "http": "http://http-only:8080", "https": "https://https-only:8443"}
        )
        assert cfg.url == PROXY_URL
        assert cfg.http == "http://http-only:8080"  # type: ignore[attr-defined]
        assert cfg.https == "https://https-only:8443"  # type: ignore[attr-defined]


class TestApplyProxyEnv:
    def test_injects_when_unset(self):
        with clean_proxy_env():
            apply_proxy_env(ProxyConfig(url=PROXY_URL, no_proxy=NO_PROXY_HOSTS))
            assert os.environ["HTTP_PROXY"] == PROXY_URL
            assert os.environ["HTTPS_PROXY"] == PROXY_URL
            assert os.environ["NO_PROXY"] == ",".join(NO_PROXY_HOSTS)

    def test_does_not_overwrite_existing_uppercase(self):
        with clean_proxy_env():
            os.environ["HTTP_PROXY"] = "http://already-set:1"
            os.environ["HTTPS_PROXY"] = "http://already-set:2"
            os.environ["NO_PROXY"] = "keep-me"
            apply_proxy_env(ProxyConfig(url=PROXY_URL, no_proxy=NO_PROXY_HOSTS))
            assert os.environ["HTTP_PROXY"] == "http://already-set:1"
            assert os.environ["HTTPS_PROXY"] == "http://already-set:2"
            assert os.environ["NO_PROXY"] == "keep-me"

    def test_does_not_overwrite_existing_lowercase(self):
        with clean_proxy_env():
            os.environ["http_proxy"] = "http://lower:1"
            os.environ["https_proxy"] = "http://lower:2"
            os.environ["no_proxy"] = "lower-keep"
            apply_proxy_env(ProxyConfig(url=PROXY_URL, no_proxy=NO_PROXY_HOSTS))
            assert "HTTP_PROXY" not in os.environ
            assert "HTTPS_PROXY" not in os.environ
            assert "NO_PROXY" not in os.environ
            assert os.environ["http_proxy"] == "http://lower:1"
            assert os.environ["https_proxy"] == "http://lower:2"
            assert os.environ["no_proxy"] == "lower-keep"

    def test_partial_env_only_fills_missing(self):
        with clean_proxy_env():
            os.environ["HTTP_PROXY"] = "http://already-set:1"
            apply_proxy_env(ProxyConfig(url=PROXY_URL, no_proxy=["only-no-proxy"]))
            assert os.environ["HTTP_PROXY"] == "http://already-set:1"
            assert os.environ["HTTPS_PROXY"] == PROXY_URL
            assert os.environ["NO_PROXY"] == "only-no-proxy"

    def test_no_proxy_joined_with_commas(self):
        with clean_proxy_env():
            apply_proxy_env(ProxyConfig(no_proxy=["a", "b", "c"]))
            assert os.environ["NO_PROXY"] == "a,b,c"
            assert "HTTP_PROXY" not in os.environ

    def test_empty_config_is_noop(self):
        with clean_proxy_env():
            apply_proxy_env(ProxyConfig())
            assert not any(k in os.environ for k in _PROXY_ENV_KEYS)


class TestGetProxyHelpers:
    def test_get_proxy_url_prefers_https(self):
        with clean_proxy_env():
            os.environ["HTTP_PROXY"] = "http://http-proxy"
            os.environ["HTTPS_PROXY"] = "http://https-proxy"
            assert get_proxy_url() == "http://https-proxy"

    def test_get_requests_proxies(self):
        with clean_proxy_env():
            os.environ["HTTP_PROXY"] = "http://http-proxy"
            os.environ["HTTPS_PROXY"] = "http://https-proxy"
            assert get_requests_proxies() == {
                "http": "http://http-proxy",
                "https": "http://https-proxy",
            }

    def test_get_requests_proxies_empty(self):
        with clean_proxy_env():
            assert get_requests_proxies() == {}


class TestGetHttpxClient:
    def test_picks_up_proxy_from_env(self, mocker):
        pytest.importorskip("httpx")
        fake_client = mocker.MagicMock()
        client_cls = mocker.patch("httpx.Client", return_value=fake_client)
        with clean_proxy_env():
            os.environ["HTTPS_PROXY"] = PROXY_URL
            result = get_httpx_client(auth=None)  # avoid needing ~/.netrc
        assert result is fake_client
        assert client_cls.call_args.kwargs["proxy"] == PROXY_URL
        assert client_cls.call_args.kwargs["auth"] is None

    def test_uses_netrc_auth_when_file_exists(self, mocker, tmp_path, monkeypatch):
        httpx = pytest.importorskip("httpx")
        netrc_file = tmp_path / ".netrc"
        netrc_file.write_text("machine proxy.example.com\nlogin u\npassword p\n")
        monkeypatch.setenv("HOME", str(tmp_path))
        client_cls = mocker.patch("httpx.Client", return_value=mocker.MagicMock())
        with clean_proxy_env():
            get_httpx_client()
        auth = client_cls.call_args.kwargs.get("auth")
        assert isinstance(auth, httpx.NetRCAuth)

    def test_explicit_proxy_kwarg_wins(self, mocker):
        pytest.importorskip("httpx")
        client_cls = mocker.patch("httpx.Client", return_value=mocker.MagicMock())
        with clean_proxy_env():
            os.environ["HTTPS_PROXY"] = "http://from-env:8080"
            get_httpx_client(proxy="http://from-kwarg:8080", auth=None)
        assert client_cls.call_args.kwargs["proxy"] == "http://from-kwarg:8080"

    def test_exported_from_ape_utils(self):
        from ape.utils import get_httpx_client as exported

        assert exported is get_httpx_client


class TestConfigManagerProxyBootstrap:
    """Ensure merge_with_global injects proxy env (CLI / import ape path)."""

    def test_merge_with_global_applies_proxy(self, config):
        with clean_proxy_env():
            project_cfg = ApeConfig.model_validate(
                {"proxy": {"url": PROXY_URL, "no_proxy": ["localhost"]}}
            )
            merged = config.merge_with_global(project_cfg)
            assert merged.proxy.url == PROXY_URL
            assert os.environ["HTTP_PROXY"] == PROXY_URL
            assert os.environ["HTTPS_PROXY"] == PROXY_URL
            assert os.environ["NO_PROXY"] == "localhost"

    def test_merge_does_not_clobber_existing_env(self, config):
        with clean_proxy_env():
            os.environ["HTTP_PROXY"] = "http://sysadmin:8080"
            project_cfg = ApeConfig.model_validate({"proxy": {"url": PROXY_URL}})
            config.merge_with_global(project_cfg)
            assert os.environ["HTTP_PROXY"] == "http://sysadmin:8080"
            # HTTPS was unset, so config may fill it.
            assert os.environ["HTTPS_PROXY"] == PROXY_URL
