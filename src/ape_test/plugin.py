#!/usr/bin/python3

import sys
from pathlib import Path

from .fixtures import PytestApeFixtures
from .managers import PytestApeRunner, PytestApeXdistManager, PytestApeXdistRunner


# set commandline options
def pytest_addoption(parser):
    parser.addoption(
        "--revert-tb", "-R", action="store_true", help="Show detailed traceback on tx reverts"
    )
    parser.addoption(
        "--showinternal",
        action="store_true",
        help="Include Ape internal frames in tracebacks",
    )
    # NOTE: Other testing plugins should integrate with pytest separately


def pytest_configure(config):
    # do not include ape internals in tracebacks unless explicitly asked
    if not config.getoption("showinternal"):
        base_path = Path(sys.modules["ape"].__file__).parent.as_posix()
        for module in [
            v
            for v in sys.modules.values()
            if getattr(v, "__file__", None) and v.__file__.startswith(base_path)
        ]:
            module.__tracebackhide__ = True

    # enable verbose output if stdout capture is disabled
    if config.getoption("capture") == "no":
        config.option.verbose = True

    # If xdist is installed, register the master runner
    has_xdist = "numprocesses" in config.option
    if has_xdist and config.getoption("numprocesses"):
        Plugin = PytestApeXdistManager

    # Manager runner needs to use Child Process runners
    elif hasattr(config, "workerinput"):
        Plugin = PytestApeXdistRunner

    # X-dist not installed or disabled, using the normal runner
    else:
        Plugin = PytestApeRunner

    # Inject the runner plugin (must happen before fixtures registration)
    session = Plugin()  # NOTE: contains the injected local project
    config.pluginmanager.register(session, "ape-core")

    # Only inject fixtures if we're not configuring the x-dist master runner
    if not has_xdist or not config.getoption("numprocesses"):
        fixtures = PytestApeFixtures()  # NOTE: contains all the registered fixtures
        config.pluginmanager.register(fixtures, "ape-fixtures")
