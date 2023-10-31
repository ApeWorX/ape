import sys
from pathlib import Path

import pytest

from ape import networks, project
from ape.exceptions import ConfigError
from ape.logging import LogLevel, logger
from ape.pytest.config import ConfigWrapper
from ape.pytest.coverage import CoverageTracker
from ape.pytest.fixtures import PytestApeFixtures, ReceiptCapture
from ape.pytest.gas import GasTracker
from ape.pytest.runners import PytestApeRunner
from ape.utils import ManagerAccessMixin


def pytest_addoption(parser):
    def add_option(*names, **kwargs):
        try:
            parser.addoption(*names, **kwargs)
        except ValueError as err:
            name_str = ", ".join(names)
            if "already added" in str(err):
                raise ConfigError(
                    f"Another pytest plugin besides `ape_test` uses an option with "
                    f"one of '{name_str}'. Note that Ape does not support being "
                    f"installed alongside Brownie; please use separate environments!"
                )

            raise ConfigError(f"Failed adding option {name_str}: {err}") from err

    add_option("--showinternal", action="store_true")
    add_option(
        "--network",
        action="store",
        default=networks.default_ecosystem.name,
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
    if not config.getoption("showinternal"):
        path_str = sys.modules["ape"].__file__
        if path_str:
            base_path = Path(path_str).parent.as_posix()

            def is_module(v):
                return getattr(v, "__file__", None) and v.__file__.startswith(base_path)

            modules = [v for v in sys.modules.values() if is_module(v)]
            for module in modules:
                if hasattr(module, "__tracebackhide__"):
                    setattr(module, "__tracebackhide__", True)

    config_wrapper = ConfigWrapper(config)
    receipt_capture = ReceiptCapture(config_wrapper)
    gas_tracker = GasTracker(config_wrapper)
    coverage_tracker = CoverageTracker(config_wrapper)

    # Enable verbose output if stdout capture is disabled
    config.option.verbose = config.getoption("capture") == "no"

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


def pytest_load_initial_conftests(early_config):
    """
    Compile contracts before loading ``conftest.py``s.
    """
    capture_manager = early_config.pluginmanager.get_plugin("capturemanager")

    if not project.sources_missing:
        # Suspend stdout capture to display compilation data
        capture_manager.suspend()
        try:
            project.load_contracts()
        except Exception as err:
            logger.log_debug_stack_trace()
            message = "Unable to load project. "
            if logger.level > LogLevel.DEBUG:
                message = f"{message}Use `-v DEBUG` to see more info.\n"

            message = f"{message}Failure reason: ({type(err).__name__}) {err}"
            raise pytest.UsageError(message)

        finally:
            capture_manager.resume()
