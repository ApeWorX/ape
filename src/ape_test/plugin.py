import sys
from pathlib import Path

import pytest
from _pytest.config import Config

from ape import accounts, networks, project
from ape_test.fixtures import PytestApeFixtures
from ape_test.runners import PytestApeRunner


def pytest_addoption(parser):
    parser.addoption(
        "--showinternal",
        action="store_true",
        default=networks.default_ecosystem.name,
        help="Override the default network and provider. (see ``ape networks list`` for options)",
    )
    parser.addoption("--network", action="store", help="The network to run the tests on.")
    # NOTE: Other testing plugins should integrate with pytest separately


def _get_runner_class(config: Config):
    has_xdist = "numprocesses" in config.option
    if has_xdist and config.getoption("numprocesses"):
        raise NotImplementedError("x-dist support has not been implemented.")

    return PytestApeRunner


def pytest_configure(config):
    # Do not include ape internals in tracebacks unless explicitly asked
    if not config.getoption("showinternal"):
        base_path = Path(sys.modules["ape"].__file__).parent.as_posix()

        def is_module(v):
            return getattr(v, "__file__", None) and v.__file__.startswith(base_path)

        modules = [v for v in sys.modules.values() if is_module(v)]
        for module in modules:
            module.__tracebackhide__ = True

    # Enable verbose output if stdout capture is disabled
    config.option.verbose = config.getoption("capture") == "no"

    # Inject the runner plugin (must happen before fixtures registration)
    session = PytestApeRunner(config, project, networks)
    config.pluginmanager.register(session, "ape-test")

    # Only inject fixtures if we're not configuring the x-dist master runner
    has_xdist = "numprocesses" in config.option
    if not has_xdist or not config.getoption("numprocesses"):
        fixtures = PytestApeFixtures(accounts, networks, project)
        config.pluginmanager.register(fixtures, "ape-fixtures")


def pytest_load_initial_conftests(early_config):
    """
    Compile contracts before loading conftests.
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
