from pathlib import Path
from typing import TYPE_CHECKING, Optional

import click
import pytest
from _pytest._code.code import Traceback as PytestTraceback
from rich import print as rich_print

from ape.exceptions import ConfigError, ProviderNotConnectedError
from ape.logging import LogLevel
from ape.pytest.utils import Scope
from ape.utils.basemodel import ManagerAccessMixin

if TYPE_CHECKING:
    from ape.api.networks import ProviderContextManager
    from ape.pytest.config import ConfigWrapper
    from ape.pytest.coverage import CoverageTracker
    from ape.pytest.fixtures import FixtureManager, IsolationManager, ReceiptCapture
    from ape.pytest.gas import GasTracker
    from ape.types.coverage import CoverageReport


class PytestApeRunner(ManagerAccessMixin):
    def __init__(
        self,
        config_wrapper: "ConfigWrapper",
        isolation_manager: "IsolationManager",
        receipt_capture: "ReceiptCapture",
        gas_tracker: "GasTracker",
        coverage_tracker: "CoverageTracker",
        fixture_manager: Optional["FixtureManager"] = None,
    ):
        self.config_wrapper = config_wrapper
        self.isolation_manager = isolation_manager
        self.receipt_capture = receipt_capture
        self._provider_is_connected = False

        # Ensure the gas report starts off None for this runner.
        gas_tracker.session_gas_report = None
        self.gas_tracker = gas_tracker
        self.coverage_tracker = coverage_tracker

        if fixture_manager is None:
            from ape.pytest.fixtures import FixtureManager

            self.fixture_manager = FixtureManager(config_wrapper, isolation_manager)

        else:
            self.fixture_manager = fixture_manager

        self._initialized_fixtures: list[str] = []
        self._finalized_fixtures: list[str] = []

    @property
    def _provider_context(self) -> "ProviderContextManager":
        return self.network_manager.parse_network_choice(self.config_wrapper.network)

    @property
    def _coverage_report(self) -> Optional["CoverageReport"]:
        return self.coverage_tracker.data.report if self.coverage_tracker.data else None

    def pytest_exception_interact(self, report, call):
        """
        A ``-I`` option triggers when an exception is raised which can be interactively handled.
        Outputs the full ``repr`` of the failed test and opens an interactive shell using the
        same console as the ``ape console`` command.
        """

        # Find the last traceback frame within the active project
        tb_frames: PytestTraceback = call.excinfo.traceback
        base = self.local_project.path.as_posix()

        if self.config_wrapper.show_internal:
            relevant_tb = list(tb_frames)
        else:
            relevant_tb = [
                f
                for f in tb_frames
                if Path(f.path).as_posix().startswith(base) or Path(f.path).name.startswith("test_")
            ]

        if relevant_tb:
            call.excinfo.traceback = PytestTraceback(relevant_tb)

            # Only show locals if not digging into the framework's traceback.
            # Else, it gets way too noisy.
            show_locals = not self.config_wrapper.show_internal

            try:
                here = Path.cwd()

            except FileNotFoundError:
                pass  # In a temp-folder, most likely.

            else:
                report.longrepr = call.excinfo.getrepr(
                    funcargs=True,
                    abspath=here,
                    showlocals=show_locals,
                    style="short",
                    tbfilter=False,
                    truncate_locals=True,
                    chain=False,
                )

        if self.config_wrapper.interactive and report.failed:
            from ape_console._cli import console

            traceback = call.excinfo.traceback[-1]

            # Suspend capsys to ignore our own output.
            capman = self.config_wrapper.get_pytest_plugin("capturemanager")
            if capman:
                capman.suspend_global_capture(in_=True)

            # Show the exception info before launching the interactive session.
            click.echo()
            rich_print(str(report.longrepr))
            click.echo()

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

            click.echo("Starting interactive mode. Type `exit` to halt current test.")

            namespace = {"_callinfo": call, **globals_dict, **locals_dict}

            console(extra_locals=namespace, project=self.local_project, embed=True)

            if capman:
                capman.resume_global_capture()

        if type(call.excinfo.value) in (SystemExit, KeyboardInterrupt):
            # This will show the rest of Ape Test output as if the
            # tests had stopped here.
            pytest.exit("`ape test` exited.")

    def pytest_runtest_setup(self, item):
        """
        By default insert isolation fixtures into each test cases list of fixtures
        prior to actually executing the test case.

        https://docs.pytest.org/en/6.2.x/reference.html#pytest.hookspec.pytest_runtest_setup
        """
        if (
            not self.config_wrapper.isolation
            # doctests don't have fixturenames
            or (hasattr(pytest, "DoctestItem") and isinstance(item, pytest.DoctestItem))
            or "_function_isolation" in item.fixturenames  # prevent double injection
        ):
            # isolation is disabled via cmdline option or running doc-tests.
            return

        if self.config_wrapper.isolation:
            self._setup_isolation(item)

    def _setup_isolation(self, item):
        fixtures = self.fixture_manager.get_fixtures(item)
        for scope in (Scope.SESSION, Scope.PACKAGE, Scope.MODULE, Scope.CLASS):
            if not (
                custom_fixtures := [f for f in fixtures[scope] if self.fixture_manager.is_custom(f)]
            ):
                # Intermediate scope isolations aren't filled in, or only using
                # built-in Ape fixtures.
                continue

            snapshot = self.isolation_manager.get_snapshot(scope)

            # Gather new fixtures. Also, be mindful of parametrized fixtures
            # which strangely have the same name.
            new_fixtures = []
            for custom_fixture in custom_fixtures:
                # Parametrized fixtures must always be considered new
                # because of severe complications of using them.
                is_custom = custom_fixture in fixtures.parametrized
                is_iterating = is_custom and fixtures.is_iterating(custom_fixture)
                is_new = custom_fixture not in snapshot.fixtures

                # NOTE: Consider ``None`` to be stateful here to be safe.
                stateful = self.fixture_manager.is_stateful(custom_fixture) is not False

                if (is_new or is_iterating) and stateful:
                    new_fixtures.append(custom_fixture)
                    continue

            # Rebase if there are new fixtures found of non-function scope.
            # And there are stateful fixtures of lower scopes that need resetting.
            may_need_rebase = bool(new_fixtures and snapshot.fixtures)
            if may_need_rebase:
                self.fixture_manager.rebase(scope, fixtures)

            # Append these fixtures so we know when new ones arrive
            # and need to trigger the invalidation logic above.
            snapshot.append_fixtures(new_fixtures)

        fixtures.apply_fixturenames()

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
        if not reporter:
            return

        warnings = reporter.stats.pop("warnings", [])
        warnings = [i for i in warnings if "PytestAssertRewriteWarning" not in i.message]
        if warnings and not self.config_wrapper.disable_warnings:
            reporter.stats["warnings"] = warnings

    @pytest.hookimpl(tryfirst=True, hookwrapper=True)
    def pytest_runtest_call(self, item):
        if network_marker := item.get_closest_marker("use_network"):
            if len(getattr(network_marker, "args", []) or []) != 1:
                raise ValueError("`use_network` marker requires single network choice argument.")

            with self.network_manager.parse_network_choice(network_marker.args[0]):
                yield

        else:
            yield

    def pytest_fixture_setup(self, fixturedef, request):
        fixture_name = fixturedef.argname
        if fixture_name in self._initialized_fixtures:
            return

        self._initialized_fixtures.append(fixture_name)
        if self._track_fixture_blocks(fixture_name):
            try:
                block_number = self.chain_manager.blocks.height
            except Exception:
                pass
            else:
                self.fixture_manager.add_fixture_info(fixture_name, setup_block=block_number)

    def pytest_fixture_post_finalizer(self, fixturedef, request):
        fixture_name = fixturedef.argname
        if fixture_name in self._finalized_fixtures:
            return

        self._finalized_fixtures.append(fixture_name)
        if self._track_fixture_blocks(fixture_name):
            try:
                block_number = self.chain_manager.blocks.height
            except ProviderNotConnectedError:
                pass
            else:
                self.fixture_manager.add_fixture_info(fixture_name, teardown_block=block_number)

    def _track_fixture_blocks(self, fixture_name: str) -> bool:
        if not self.fixture_manager.is_custom(fixture_name):
            return False

        scope = self.fixture_manager.get_fixture_scope(fixture_name)
        if scope in (None, Scope.FUNCTION):
            return False

        return True

    @pytest.hookimpl(trylast=True, hookwrapper=True)
    def pytest_collection_finish(self, session):
        """
        Called after collection has been performed and modified.
        """
        outcome = yield

        # Only start provider if collected tests.
        if not outcome.get_result() and session.items:
            self._connect()

    def _connect(self):
        if self._provider_context._provider.network.is_mainnet:
            # Ensure is not only running on tests on mainnet because
            # was configured as the default.
            is_from_command_line = (
                "--network" in self.config_wrapper.pytest_config.invocation_params.args
            )
            if not is_from_command_line:
                raise ConfigError(
                    "Default network is mainnet; unable to run tests on mainnet. "
                    "Please specify the network using the `--network` flag or "
                    "configure a different default network."
                )

        self._provider_context.push_provider()
        self._provider_is_connected = True

    def pytest_terminal_summary(self, terminalreporter):
        """
        Add a section to terminal summary reporting.
        When ``--gas`` is active, outputs the gas profile report.
        """
        if self.config_wrapper.track_gas:
            self._show_gas_report(terminalreporter)
        if self.config_wrapper.track_coverage:
            self._show_coverage_report(terminalreporter)

    def _show_gas_report(self, terminalreporter):
        terminalreporter.section("Gas Profile")
        if not self.network_manager.active_provider:
            # Happens if never needed to connect (no tests)
            return

        self._log_tracing_support(
            terminalreporter, "The gas profile is limited to receipt-level data."
        )
        if not self.gas_tracker.show_session_gas():
            terminalreporter.write_line(
                f"{LogLevel.WARNING.name}: No gas usage data found.", yellow=True
            )

    def _show_coverage_report(self, terminalreporter):
        if self.config_wrapper.ape_test_config.coverage.reports.terminal:
            terminalreporter.section("Coverage Profile")

        if not self.network_manager.active_provider:
            # Happens if never needed to connect (no tests)
            return

        self._log_tracing_support(
            terminalreporter, "Coverage is limited to receipt-level function coverage."
        )
        if not self.coverage_tracker.show_session_coverage():
            terminalreporter.write_line(
                f"{LogLevel.WARNING.name}: No coverage data found. "
                f"Try re-compiling your contracts using the latest compiler plugins",
                yellow=True,
            )

    def _log_tracing_support(self, terminalreporter, extra_warning: str):
        if self.provider.supports_tracing:
            return

        message = (
            f"{LogLevel.ERROR.name}: Provider '{self.provider.name}' does not support "
            f"transaction tracing. {extra_warning}"
        )
        terminalreporter.write_line(message, red=True)

    def pytest_unconfigure(self):
        if self._provider_is_connected and self.config_wrapper.disconnect_providers_after:
            self._provider_context.disconnect_all()
            self._provider_is_connected = False

        # NOTE: Clearing the state is helpful for pytester-based tests,
        #  which may run pytest many times in-process.
        self.receipt_capture.clear()
        self.chain_manager.contracts.clear_local_caches()
        self.gas_tracker.session_gas_report = None
        self.coverage_tracker.reset()
