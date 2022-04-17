from pathlib import Path

import click
import pytest
from _pytest.config import Config as PytestConfig

import ape
from ape.logging import logger
from ape.utils import ManagerAccessMixin
from ape_console._cli import console

from .contextmanagers import RevertsContextManager


class PytestApeRunner(ManagerAccessMixin):
    def __init__(
        self,
        pytest_config: PytestConfig,
    ):
        self.pytest_config = pytest_config
        self._provider_is_connected = False
        ape.reverts = RevertsContextManager  # type: ignore

    @property
    def _network_choice(self) -> str:
        # The option the user providers via --network (or the default).
        return self.pytest_config.getoption("network")

    def pytest_exception_interact(self, report, call):
        """
        A ``-I`` option triggers when an exception is raised which can be interactively handled.
        Outputs the full ``repr`` of the failed test and opens an interactive shell using the
        same console as the ``ape console`` command.
        """

        if self.pytest_config.getoption("interactive") and report.failed:

            capman = self.pytest_config.pluginmanager.get_plugin("capturemanager")
            if capman:
                capman.suspend_global_capture(in_=True)

            # find the last traceback frame within the active project
            traceback = call.excinfo.traceback[-1]
            for tb_frame in call.excinfo.traceback[::-1]:
                try:
                    Path(tb_frame.path).relative_to(self.project_manager.path)
                    traceback = tb_frame
                    click.echo()
                    click.echo(f"Traceback:{traceback}")
                    break
                except ValueError as err:
                    click.echo()
                    logger.warn_from_exception(err, tb_frame)
                    pass

            # get global namespace
            globals_dict = traceback.frame.f_globals

            # filter python internals and pytest internals
            globals_dict = {
                k: v
                for k, v in globals_dict.items()
                if not k.startswith("__") and not k.startswith("@")
            }

            # filter fixtures
            globals_dict = {
                k: v for k, v in globals_dict.items() if not hasattr(v, "_pytestfixturefunction")
            }

            # get local namespace
            locals_dict = traceback.locals
            locals_dict = {k: v for k, v in locals_dict.items() if not k.startswith("@")}

            click.echo("Starting interactive mode. Type `exit` fail and halt current test.")

            namespace = {"_callinfo": call, **globals_dict, **locals_dict}
            console(extra_locals=namespace, project=self.project_manager)

            # launch ipdb instead of console
            if capman:
                capman.resume_global_capture()

    def pytest_runtest_setup(self, item):
        """
        By default insert isolation fixtures into each test cases list of fixtures
        prior to actually executing the test case.

        https://docs.pytest.org/en/6.2.x/reference.html#pytest.hookspec.pytest_runtest_setup
        """
        if self.pytest_config.getoption("disable_isolation") is True:
            # isolation is disabled via cmdline option
            return

        # list of scopes for each fixture of the test
        scopes = [item._fixtureinfo.name2fixturedefs[f][0].scope for f in item.fixturenames]

        idx = 0
        for scope in ["session", "package", "module", "class"]:
            # iterate through scope levels and insert the isolation fixture
            # prior to the first fixture with that scope
            try:
                idx = scopes.index(scope, idx)
            except ValueError:
                # intermediate scope isolations are filled in by later fixtures
                # even if they are skipped (which will only happen if no fixture
                # is defined at that scope level)
                continue
            item.fixturenames.insert(idx, f"_{scope}_isolation")
            scopes.insert(idx, scope)

        # lastly insert function isolation
        try:
            item.fixturenames.insert(scopes.index("function", idx), "_function_isolation")
        except ValueError:
            item.fixturenames.append("_function_isolation")

    def pytest_sessionstart(self):
        """
        Called after the `Session` object has been created and before performing
        collection and entering the run test loop.

        Removes `PytestAssertRewriteWarning` warnings from the terminalreporter.
        This prevents warnings that "the `ape` library was already imported and
        so related assertions cannot be rewritten". The warning is not relevant
        for end users who are performing tests with ape.
        """
        reporter = self.pytest_config.pluginmanager.get_plugin("terminalreporter")
        warnings = reporter.stats.pop("warnings", [])
        warnings = [i for i in warnings if "PytestAssertRewriteWarning" not in i.message]
        if warnings and not self.pytest_config.getoption("--disable-warnings"):
            reporter.stats["warnings"] = warnings

    @pytest.hookimpl(trylast=True, hookwrapper=True)
    def pytest_collection_finish(self, session):
        """
        Called after collection has been performed and modified.
        """
        outcome = yield

        # Only start provider if collected tests.
        if not outcome.get_result() and session.items and not self.network_manager.active_provider:
            self.network_manager.active_provider = self.network_manager.get_provider_from_choice(
                self._network_choice
            )
            self.network_manager.active_provider.connect()
            self._provider_is_connected = True

    def pytest_sessionfinish(self):
        """
        Called after whole test run finished, right before returning the exit
        status to the system.

        **NOTE**: This hook fires even when exceptions occur, so we cannot
        assume the provider successfully connected.
        """
        if self._provider_is_connected:
            self.chain_manager.provider.disconnect()
            self._provider_is_connected = False
