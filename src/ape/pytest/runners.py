import inspect
from collections import defaultdict
from collections.abc import Iterable
from functools import cached_property, singledispatchmethod
from pathlib import Path
from typing import Optional

import click
import pytest
from _pytest._code.code import Traceback as PytestTraceback
from rich import print as rich_print

from ape.api.networks import ProviderContextManager
from ape.logging import LogLevel
from ape.pytest.config import ConfigWrapper
from ape.pytest.coverage import CoverageTracker
from ape.pytest.fixtures import IsolationManager, PytestApeFixtures, ReceiptCapture
from ape.pytest.gas import GasTracker
from ape.pytest.utils import Scope
from ape.types.coverage import CoverageReport
from ape.utils.basemodel import ManagerAccessMixin
from ape_console._cli import console


class FixturesByScope(dict[Scope, list[str]]):
    def __init__(self):
        super().__init__(
            {
                Scope.SESSION: [],
                Scope.PACKAGE: [],
                Scope.MODULE: [],
                Scope.CLASS: [],
                Scope.FUNCTION: [],
            }
        )

    @singledispatchmethod
    def __setitem__(self, key, value):
        raise NotImplementedError(type(key))

    @__setitem__.register
    def __setitem_int(self, key: int, value: list[str]):
        super().__setitem__(Scope(key), value)

    @__setitem__.register
    def __setitem_str(self, key: str, value: list[str]):
        for scope in Scope:
            if f"{scope}" == key:
                super().__setitem__(scope, value)
                return

        raise KeyError(key)

    @__setitem__.register
    def __setitem_scope(self, key: Scope, value: list[str]):
        super().__setitem__(key, value)

    @singledispatchmethod
    def __getitem__(self, key):
        raise NotImplementedError(type(key))

    @__getitem__.register
    def __getitem_int(self, key: int) -> list[str]:
        return super().__getitem__(Scope(key))

    @__getitem__.register
    def __getitem_str(self, key: str) -> list[str]:
        for scope in Scope:
            if f"{scope}" == key:
                return super().__getitem__(scope)

        raise KeyError(key)

    @__getitem__.register
    def __getitem_scope(self, key: Scope) -> list[str]:
        return super().__getitem__(key)

    @classmethod
    def from_test_item(cls, item) -> "FixturesByScope":
        obj = cls()
        info_dict = item.session._fixturemanager._arg2fixturedefs
        for name, info_ls in info_dict.items():
            if not info_ls or name not in item.fixturenames:
                continue

            for info in info_ls:
                obj[info.scope].append(name)

        return obj

    @property
    def fixturenames(self) -> list[str]:
        """
        Outputs in correct order for item.fixturenames.
        Also, injects isolation fixtures if needed.
        """
        result = []
        for scope, ls in self.items():
            # NOTE: For function scoped, we always add the isolation fixture.
            if not ls and scope is not Scope.FUNCTION:
                continue

            result.append(scope.isolation_fixturename)
            result.extend(ls)

        return result

    def prepend(self, scope: Scope, fixtures: Iterable[str]):
        existing = self[scope]
        result = []
        for new_fixture in fixtures:
            if new_fixture in existing:
                existing.remove(new_fixture)

            result.append(new_fixture)

        for existing_fixture in existing:
            result.append(existing_fixture)

        self[scope] = result


class PytestApeRunner(ManagerAccessMixin):
    def __init__(
        self,
        config_wrapper: ConfigWrapper,
        isolation_manager: IsolationManager,
        receipt_capture: ReceiptCapture,
        gas_tracker: GasTracker,
        coverage_tracker: CoverageTracker,
    ):
        self.config_wrapper = config_wrapper
        self.isolation_manager = isolation_manager
        self.receipt_capture = receipt_capture
        self._provider_is_connected = False
        self._builtin_fixtures: list[str] = []

        # Ensure the gas report starts off None for this runner.
        gas_tracker.session_gas_report = None
        self.gas_tracker = gas_tracker
        self.coverage_tracker = coverage_tracker

    @property
    def _provider_context(self) -> ProviderContextManager:
        return self.network_manager.parse_network_choice(self.config_wrapper.network)

    @property
    def _coverage_report(self) -> Optional[CoverageReport]:
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

            report.longrepr = call.excinfo.getrepr(
                funcargs=True,
                abspath=Path.cwd(),
                showlocals=show_locals,
                style="short",
                tbfilter=False,
                truncate_locals=True,
                chain=False,
            )

        if self.config_wrapper.interactive and report.failed:
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

    @cached_property
    def _ape_fixtures(self) -> tuple[str, ...]:
        return tuple(
            [
                n
                for n, itm in inspect.getmembers(PytestApeFixtures)
                if callable(itm) and not n.startswith("_")
            ]
        )

    def _get_builtin_fixtures(self, item) -> list[str]:
        if self._builtin_fixtures:
            return self._builtin_fixtures

        self._builtin_fixtures = [
            fixture_name
            for fixture_name, defs in item.session._fixturemanager._arg2fixturedefs.items()
            if any("pytest" in fixture.func.__module__ for fixture in defs)
        ]
        return self._builtin_fixtures

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

        fixture_defs = item.session._fixturemanager._arg2fixturedefs
        fixture_by_scope = FixturesByScope.from_test_item(item)
        builtin_fixtures = self._get_builtin_fixtures(item)
        for scope in (Scope.SESSION, Scope.PACKAGE, Scope.MODULE, Scope.CLASS):
            custom_fixtures = [
                f
                for f in fixture_by_scope[scope]
                if f not in self._ape_fixtures and f not in builtin_fixtures
            ]
            if not custom_fixtures:
                # Intermediate scope isolations aren't filled in, or only using
                # built-in Ape fixtures.
                continue

            snapshot = self.isolation_manager.get_snapshot(scope)

            # Gather new fixtures. Also, be mindful of parametrized fixtures
            # which strangely have the same name.
            new_fixtures = []
            for custom_fixture in custom_fixtures:
                if custom_fixture not in snapshot.fixtures:
                    # Is simply a new a fixture.
                    new_fixtures.append(custom_fixture)
                    continue

                elif custom_fixture not in fixture_defs:
                    # Unknown fixture?
                    continue

                fixture_infos = fixture_defs[custom_fixture]

                # Check for parametrized fixtures, which have special handling.
                for fixture_info in fixture_infos:
                    params = fixture_info.params
                    if params is None:
                        # Not a parametrized fixture.
                        continue

                    cached_result = fixture_info.cached_result
                    if cached_result is None:
                        # If we get here, we already checked we hadn't seen this
                        # fixture before. Yet, it has no cached result and is not
                        # function-scoped fixture. Is it even possible to get
                        # to this state? It would require hitting the same iteration of
                        # a parametrized fixture twice. Ignore for now.
                        continue

                    last_known_fixture_param = cached_result[1]
                    number_of_parameters = len(params)
                    if number_of_parameters <= 1 and last_known_fixture_param != params[-2]:
                        continue

                    # If we are here, this parametrized fixture has multiple returns (params>1),
                    # and this is the last iteration of that return. We can treat this
                    # situation the same as if a more fixtures of a certain scope coming
                    # in late.
                    new_fixtures.append(custom_fixture)

            # Check for fixtures that are now invalid. For example, imagine a session
            # fixture comes into play after the module snapshot has been set.
            # Once we restore the module's state and move to the next module,
            # that session fixture will no longer exist. To remedy this situation,
            # we invalidate the lower-scoped fixtures and re-snapshot everything.
            if new_fixtures and snapshot.fixtures:
                invalid_fixtures = defaultdict(list)
                scope_to_revert = None
                for next_snapshot in self.isolation_manager.next_snapshots(scope):
                    if next_snapshot.identifier is None:
                        # Thankfully, we haven't reached this scope yet.
                        # In this case, things are running in a performant order.
                        continue

                    if scope_to_revert is None:
                        # Revert to the closest scope to use. For example, a new
                        # session comes in but we have already calculated a module
                        # and a class, revert to pre-module and invalidate the module
                        # and class fixtures.
                        scope_to_revert = next_snapshot.scope

                    # All fixtures downward need to be invalidated.
                    invalid_fixtures[next_snapshot.scope].extend(next_snapshot.fixtures)

                # Restore the state now.
                if scope_to_revert is not None:
                    self.isolation_manager.restore(scope_to_revert)

                # Invalidate fixtures by clearing out their cached result.
                for invalid_scope, invalid_fixture_ls in invalid_fixtures.items():
                    for invalid_fixture in invalid_fixture_ls:
                        if invalid_fixture not in fixture_defs:
                            continue

                        info_ls = fixture_defs[invalid_fixture]
                        for info in info_ls:
                            info.cached_result = None

                    # Also, invalidate the corresponding isolation fixture.
                    if invalid_isolation_fixture_ls := fixture_defs.get(
                        invalid_scope.isolation_fixturename
                    ):
                        for invalid_isolation_fixture in invalid_isolation_fixture_ls:
                            invalid_isolation_fixture.cached_result = None

            # Append these fixtures so we know when new ones arrive
            # and need to trigger the invalidation logic above.
            snapshot.append_fixtures(new_fixtures)

        # Finally, setting the fixturenames in the order they should be used.
        # Pytest runs the fixtures in this order.
        item.fixturenames = fixture_by_scope.fixturenames

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

    @pytest.hookimpl(trylast=True, hookwrapper=True)
    def pytest_collection_finish(self, session):
        """
        Called after collection has been performed and modified.
        """
        outcome = yield

        # Only start provider if collected tests.
        if not outcome.get_result() and session.items:
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
