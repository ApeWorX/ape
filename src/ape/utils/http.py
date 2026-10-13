"""
HTTP client helpers, including proxy configuration support.

See :class:`~ape.api.config.ProxyConfig` and the ``proxy`` section of
``ape-config.yaml``. Environment variables ``HTTP_PROXY`` / ``HTTPS_PROXY`` /
``NO_PROXY`` / ``ALL_PROXY`` (and lowercase variants) always take precedence
over config when already set.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import httpx

    from ape.api.config import ProxyConfig

# Canonical uppercase names first; lowercase checked for "already set".
_HTTP_PROXY_KEYS = ("HTTP_PROXY", "http_proxy")
_HTTPS_PROXY_KEYS = ("HTTPS_PROXY", "https_proxy")
_ALL_PROXY_KEYS = ("ALL_PROXY", "all_proxy")
_NO_PROXY_KEYS = ("NO_PROXY", "no_proxy")


def _env_is_set(keys: tuple[str, ...]) -> bool:
    return any(key in os.environ for key in keys)


def _set_env_if_unset(keys: tuple[str, ...], value: str) -> None:
    """Write ``keys[0]`` (canonical uppercase) only when none of ``keys`` exist."""
    if _env_is_set(keys):
        return

    os.environ[keys[0]] = value


def apply_proxy_env(proxy: ProxyConfig) -> None:
    """
    Inject proxy settings from Ape config into ``os.environ`` when unset.

    Existing ``HTTP_PROXY`` / ``HTTPS_PROXY`` / ``NO_PROXY`` / ``ALL_PROXY``
    (and lowercase variants) are never overwritten so sysadmins / IT can
    control networking at the OS level.

    Args:
        proxy (:class:`~ape.api.config.ProxyConfig`): Parsed proxy config.
    """
    if proxy.url:
        # Flat ``url`` today seeds both HTTP and HTTPS; future per-protocol
        # keys (``http``, ``https``) can extend this without breaking callers.
        _set_env_if_unset(_HTTP_PROXY_KEYS, proxy.url)
        _set_env_if_unset(_HTTPS_PROXY_KEYS, proxy.url)

    if proxy.no_proxy:
        _set_env_if_unset(_NO_PROXY_KEYS, ",".join(proxy.no_proxy))


def get_proxy_url() -> str | None:
    """
    Resolve the active proxy URL from the environment (after config injection).

    Returns:
        str | None: Prefer HTTPS, then HTTP, then ALL_PROXY.
    """
    for keys in (_HTTPS_PROXY_KEYS, _HTTP_PROXY_KEYS, _ALL_PROXY_KEYS):
        for key in keys:
            if value := os.environ.get(key):
                return value

    return None


def get_requests_proxies() -> dict[str, str]:
    """
    Build a ``requests``-style ``proxies`` mapping from the environment.

    Returns:
        dict[str, str]: May be empty when no proxy env vars are set.
    """
    proxies: dict[str, str] = {}

    http = os.environ.get("HTTP_PROXY") or os.environ.get("http_proxy")
    https = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("ALL_PROXY")
        or os.environ.get("all_proxy")
        or http
    )
    if http:
        proxies["http"] = http
    if https:
        proxies["https"] = https

    return proxies


def get_httpx_client(**kwargs) -> httpx.Client:
    """
    Construct an :class:`~httpx.Client` with Ape proxy and ``.netrc`` defaults.

    Unlike ``requests``, ``httpx`` does not automatically apply ``.netrc``
    credentials; this helper opts in via :class:`httpx.NetRCAuth` when
    available. Proxy URL is taken from kwargs, else from the environment
    (populated by :func:`apply_proxy_env` when using Ape config).

    Args:
        **kwargs: Forwarded to :class:`httpx.Client`. Explicit ``proxy`` /
            ``auth`` values override the defaults.

    Returns:
        httpx.Client: Configured client.
    """
    # Lazy import: httpx is an optional-at-import cost dependency of eth-ape.
    import httpx

    if "proxy" not in kwargs and (proxy_url := get_proxy_url()):
        kwargs["proxy"] = proxy_url

    if "auth" not in kwargs and hasattr(httpx, "NetRCAuth"):
        # Only opt in when a netrc file exists; NetRCAuth errors otherwise.
        netrc_path = Path.home() / ".netrc"
        if netrc_path.is_file():
            kwargs["auth"] = httpx.NetRCAuth(str(netrc_path))

    return httpx.Client(**kwargs)
