import sys
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ape.exceptions import ConfigError

if TYPE_CHECKING:
    from pytest import Collector


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
    add_option("--coverage", action="store_true", help="Collect contract coverage.")
    add_option("--project", action="store", help="Change Ape's project")

    # NOTE: Other pytest plugins, such as hypothesis, should integrate with pytest separately


def pytest_configure(config):
    # Do not include ape internals in tracebacks unless explicitly asked
    if not config.getoption("--show-internal") and (path_str := sys.modules["ape"].__file__):
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

    if "--help" in config.invocation_params.args:
        # perf: Don't bother setting up runner if only showing help.
        return

    from ape.pytest.config import ConfigWrapper
    from ape.pytest.coverage import CoverageTracker
    from ape.pytest.fixtures import (
        FixtureManager,
        IsolationManager,
        PytestApeFixtures,
        ReceiptCapture,
    )
    from ape.pytest.gas import GasTracker
    from ape.pytest.runners import PytestApeRunner
    from ape.utils.basemodel import ManagerAccessMixin

    if project := config.getoption("--project"):
        ManagerAccessMixin.local_project.chdir(project)

    # Register the custom Ape test runner
    config_wrapper = ConfigWrapper(config)
    receipt_capture = ReceiptCapture(config_wrapper)
    isolation_manager = IsolationManager(config_wrapper, receipt_capture)
    fixture_manager = FixtureManager(config_wrapper, isolation_manager)
    gas_tracker = GasTracker(config_wrapper)
    coverage_tracker = CoverageTracker(config_wrapper)
    runner = PytestApeRunner(
        config_wrapper,
        isolation_manager,
        receipt_capture,
        gas_tracker,
        coverage_tracker,
        fixture_manager=fixture_manager,
    )
    config.pluginmanager.register(runner, "ape-test")

    # Inject runner for access to gas and coverage trackers.
    ManagerAccessMixin._test_runner = runner

    # Include custom fixtures for project, accounts etc.
    fixtures = PytestApeFixtures(config_wrapper, isolation_manager)
    config.pluginmanager.register(fixtures, "ape-fixtures")

    # Add custom markers
    config.addinivalue_line(
        "markers", "use_network(choice): Run this test using the given network choice."
    )


# NOTE: Below is done to support contract-based compiled tests
def pytest_collect_file(parent, file_path) -> "Collector | None":
    # NOTE: Skip common files we know should not be used with this collector
    if (
        file_path.suffix in (".py", ".md", ".json")
        or len(file_path.suffixes) != 1
        or not file_path.name.startswith("test")
    ):
        return None

    from .contracts.collector import ContractTestCollector

    return ContractTestCollector.from_parent(parent, path=file_path)


def pytest_collection_modifyitems(session, config, items):
    """Order contract tests so ``@custom:ape-test-after`` predecessors run first."""
    from ape.pytest.contracts.ordering import reorder_contract_test_items

    reorder_contract_test_items(items)


@pytest.hookimpl(hookwrapper=True, tryfirst=True)
def pytest_runtest_makereport(item, call):
    """Record pass/fail/skip on contract tests so ``TEST_AFTER`` followers can skip."""
    outcome = yield
    report = outcome.get_result()
    if report.when != "call" and not (report.when == "setup" and report.skipped):
        return

    from ape.pytest.contracts.functional import ContractTestItem

    if not isinstance(item, ContractTestItem):
        return

    if report.skipped:
        item._ape_test_outcome = "skipped"
    elif report.passed and report.when == "call":
        item._ape_test_outcome = "passed"
    elif report.failed:
        item._ape_test_outcome = "failed"
