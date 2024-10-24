import sys
from pathlib import Path
from typing import Optional

from ape.api.networks import EcosystemAPI
from ape.exceptions import ConfigError
from ape.pytest.config import ConfigWrapper
from ape.pytest.coverage import CoverageTracker
from ape.pytest.fixtures import PytestApeFixtures, ReceiptCapture
from ape.pytest.gas import GasTracker
from ape.pytest.runners import PytestApeRunner
from ape.utils.basemodel import ManagerAccessMixin


def _get_default_network(ecosystem: Optional[EcosystemAPI] = None) -> str:
    if ecosystem is None:
        ecosystem = ManagerAccessMixin.network_manager.default_ecosystem

    if ecosystem.default_network.is_mainnet:
        # Don't use mainnet for tests, even if it configured as
        # the default.
        raise ConfigError(
            "Default network is mainnet; unable to run tests on mainnet. "
            "Please specify the network using the `--network` flag or "
            "configure a different default network."
        )

    return ecosystem.name


def pytest_addoption(parser):
    def add_option(*names, **kwargs):
        try:
            parser.addoption(*names, **kwargs)
        except ValueError as err:
            name_str = ", ".join(names)
            if "already added" in str(err):
                raise ConfigError(
                    "Another pytest plugin besides `ape_test` uses an option with "
                    f"one of '{name_str}'. Note that Ape does not support being "
                    "installed alongside Brownie; please use separate environments!"
                )

            raise ConfigError(f"Failed adding option {name_str}: {err}") from err

    add_option("--show-internal", action="store_true")
    add_option(
        "--network",
        action="store",
        default=_get_default_network(),
        help="Override the default network and provider (see ``ape networks list`` for options).",
    )
    add_option(
        "--interactive",
        "-I",
        action="store_true",
        help="Open an interactive console each time a test fails.",
    )
    add_option(
        "--disable-isolation",
        action="store_true",
        help="Disable test and fixture isolation (see provider for info on snapshot availability).",
    )
    add_option(
        "--gas",
        action="store_true",
        help="Show a transaction gas report at the end of the test session.",
    )
    add_option(
        "--gas-exclude",
        action="store",
        help="A comma-separated list of contract:method-name glob-patterns to ignore.",
    )
    parser.addoption("--coverage", action="store_true", help="Collect contract coverage.")

    # NOTE: Other pytest plugins, such as hypothesis, should integrate with pytest separately


def pytest_configure(config):
    # Do not include ape internals in tracebacks unless explicitly asked
    if not config.getoption("--show-internal"):
        if path_str := sys.modules["ape"].__file__:
            base_path = str(Path(path_str).parent)

            def is_module(v):
                return getattr(v, "__file__", None) and v.__file__.startswith(base_path)

            for module in (v for v in sys.modules.values() if is_module(v)):
                # NOTE: Using try/except w/ type:ignore (over checking for attr)
                #   for performance reasons!
                try:
                    module.__tracebackhide__ = True  # type: ignore[attr-defined]
                except AttributeError:
                    pass

    config_wrapper = ConfigWrapper(config)
    receipt_capture = ReceiptCapture(config_wrapper)
    gas_tracker = GasTracker(config_wrapper)
    coverage_tracker = CoverageTracker(config_wrapper)

    if not config.option.verbose:
        # Enable verbose output if stdout capture is disabled
        config.option.verbose = config.getoption("capture") == "no"
    # else: user has already changes verbosity to an equal or higher level; avoid downgrading.

    # Register the custom Ape test runner
    runner = PytestApeRunner(config_wrapper, receipt_capture, gas_tracker, coverage_tracker)
    config.pluginmanager.register(runner, "ape-test")

    # Inject runner for access to gas and coverage trackers.
    ManagerAccessMixin._test_runner = runner

    # Include custom fixtures for project, accounts etc.
    fixtures = PytestApeFixtures(config_wrapper, receipt_capture)
    config.pluginmanager.register(fixtures, "ape-fixtures")

    # Add custom markers
    config.addinivalue_line(
        "markers", "use_network(choice): Run this test using the given network choice."
    )
