from ape import plugins
from ape_test.accounts import TestAccount, TestAccountContainer
from ape_test.config import (
    ApeTestConfig,
    CoverageConfig,
    CoverageReportsConfig,
    GasConfig,
    GasExclusion,
)
from ape_test.provider import EthTesterProviderConfig, LocalProvider


@plugins.register(plugins.Config)
def config_class():
    return ApeTestConfig


@plugins.register(plugins.AccountPlugin)
def account_types():
    return TestAccountContainer, TestAccount


@plugins.register(plugins.ProviderPlugin)
def providers():
    yield "ethereum", "local", LocalProvider


__all__ = [
    "TestAccountContainer",
    "TestAccount",
    "EthTesterProviderConfig",
    "LocalProvider",
    "GasConfig",
    "GasExclusion",
    "CoverageReportsConfig",
    "CoverageConfig",
    "ApeTestConfig",
]
