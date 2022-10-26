import sys
from pathlib import Path

import pytest

from ape import networks, project
from ape.pytest.fixtures import PytestApeFixtures, ReceiptCapture
from ape.pytest.runners import PytestApeRunner


def pytest_addoption(parser):
    parser.addoption(
        "--showinternal",
        action="store_true",
    )
    parser.addoption(
        "--network",
        action="store",
        default=networks.default_ecosystem.name,
        help="Override the default network and provider (see ``ape networks list`` for options).",
    )
    parser.addoption(
        "--interactive",
        "-I",
        action="store_true",
        help="Open an interactive console each time a test fails.",
    )
    parser.addoption(
        "--disable-isolation",
        action="store_true",
        help="Disable test and fixture isolation (see provider for info on snapshot availability).",
    )
    parser.addoption(
        "--gas",
        action="store_true",
        help="Show a transaction gas report at the end of the test session.",
    )

    # NOTE: Other pytest plugins, such as hypothesis, should integrate with pytest separately


def pytest_configure(config):
    # Do not include ape internals in tracebacks unless explicitly asked
    if not config.getoption("showinternal"):
        base_path = Path(sys.modules["ape"].__file__).parent.as_posix()

        def is_module(v):
            return getattr(v, "__file__", None) and v.__file__.startswith(base_path)

        modules = [v for v in sys.modules.values() if is_module(v)]
        for module in modules:
            module.__tracebackhide__ = True

    receipt_capture = ReceiptCapture(config)

    # Enable verbose output if stdout capture is disabled
    config.option.verbose = config.getoption("capture") == "no"

    # Register the custom Ape test runner
    session = PytestApeRunner(config, receipt_capture)
    config.pluginmanager.register(session, "ape-test")

    # Include custom fixtures for project, accounts etc.
    fixtures = PytestApeFixtures(config, receipt_capture)
    config.pluginmanager.register(fixtures, "ape-fixtures")


def pytest_load_initial_conftests(early_config):
    """
    Compile contracts before loading ``conftest.py``s.
    """
    cap_sys = early_config.pluginmanager.get_plugin("capturemanager")

    if not project.sources_missing:
        # Suspend stdout capture to display compilation data
        cap_sys.suspend()
        try:
            project.load_contracts()
        except Exception as err:
            raise pytest.UsageError(f"Unable to load project. Reason: {err}")
        finally:
            cap_sys.resume()
