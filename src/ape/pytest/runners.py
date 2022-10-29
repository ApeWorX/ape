from pathlib import Path

import click
import pytest
from rich import print as rich_print

import ape
from ape.api import ProviderContextManager
from ape.logging import LogLevel, logger
from ape.pytest.config import ConfigWrapper
from ape.pytest.contextmanagers import RevertsContextManager
from ape.pytest.fixtures import ReceiptCapture
from ape.utils import ManagerAccessMixin, parse_gas_table
from ape_console._cli import console


class PytestApeRunner(ManagerAccessMixin):
    def __init__(
        self,
        config_wrapper: ConfigWrapper,
        receipt_capture: ReceiptCapture,
    ):
        self.config_wrapper = config_wrapper
        self.receipt_capture = receipt_capture
        self._provider_is_connected = False
        ape.reverts = RevertsContextManager  # type: ignore

    @property
    def _provider_context(self) -> ProviderContextManager:
        return self.network_manager.parse_network_choice(self.config_wrapper.network)

    def pytest_exception_interact(self, report, call):
        """
        A ``-I`` option triggers when an exception is raised which can be interactively handled.
        Outputs the full ``repr`` of the failed test and opens an interactive shell using the
        same console as the ``ape console`` command.
        """

        if self.config_wrapper.interactive and report.failed:
            capman = self.config_wrapper.get_pytest_plugin("capturemanager")
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
        if (
            self.config_wrapper.isolation is False
            or "_function_isolation" in item.fixturenames  # prevent double injection
        ):
            # isolation is disabled via cmdline option
            return

        fixture_map = item.session._fixturemanager._arg2fixturedefs
        scopes = [
            definition.scope
            for name, definitions in fixture_map.items()
            if name in item.fixturenames
            for definition in definitions
        ]

        for scope in ["session", "package", "module", "class"]:
            # iterate through scope levels and insert the isolation fixture
            # prior to the first fixture with that scope
            try:
                idx = scopes.index(scope)  # will raise ValueError if `scope` not found
                item.fixturenames.insert(idx, f"_{scope}_isolation")
                scopes.insert(idx, scope)
            except ValueError:
                # intermediate scope isolations aren't filled in
                continue

        # insert function isolation by default
        try:
            item.fixturenames.insert(scopes.index("function"), "_function_isolation")
        except ValueError:
            # no fixtures with function scope, so append function isolation
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
        reporter = self.config_wrapper.get_pytest_plugin("terminalreporter")
        warnings = reporter.stats.pop("warnings", [])
        warnings = [i for i in warnings if "PytestAssertRewriteWarning" not in i.message]
        if warnings and not self.config_wrapper.disable_warnings:
            reporter.stats["warnings"] = warnings

    @pytest.hookimpl(trylast=True, hookwrapper=True)
    def pytest_collection_finish(self, session):
        """
        Called after collection has been performed and modified.
        """
        outcome = yield

        # Only start provider if collected tests.
        if not outcome.get_result() and session.items and not self.network_manager.active_provider:
            self._provider_context.push_provider()
            self._provider_is_connected = True

    def pytest_terminal_summary(self, terminalreporter):
        """
        Add a section to terminal summary reporting.
        When ``--gas`` is active, outputs the gas profile report.
        """
        if self.config_wrapper.track_gas:
            terminalreporter.section("Gas Profile")

            if not self.provider.supports_tracing:
                terminalreporter.write_line(
                    f"{LogLevel.ERROR.name}: Provider '{self.provider.name}' does not support "
                    f"transaction tracing and is unable to display a gas profile.",
                    red=True,
                )
                return

            gas_report = self.receipt_capture.gas_report
            if gas_report:
                tables = parse_gas_table(gas_report)
                rich_print(*tables)
            else:

                terminalreporter.write_line(
                    f"{LogLevel.WARNING.name}: No gas usage data found.", yellow=True
                )

    def pytest_unconfigure(self):
        if self._provider_is_connected and self.config_wrapper.disconnect_providers_after:
            self._provider_context.disconnect_all()
            self._provider_is_connected = False
