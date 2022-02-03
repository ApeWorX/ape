import pytest
from _pytest.config import Config

import ape
from ape.logging import logger
from ape.utils import ManagerAccessBase

from .contextmanagers import RevertsContextManager


class PytestApeRunner(ManagerAccessBase):
    def __init__(self):
        self._warned_for_missing_features = False
        ape.reverts = RevertsContextManager  # type: ignore

    @pytest.hookimpl(hookwrapper=True)
    def pytest_runtest_protocol(self, item, nextitem):
        snapshot_id = None

        # Try to snapshot if the provider supported it.
        try:
            snapshot_id = self.chain_manager.snapshot()
        except NotImplementedError:
            self._warn_for_unimplemented_snapshot()
            pass

        yield

        # Try to revert to the state before the test began.
        if snapshot_id:
            self.chain_manager.restore(snapshot_id)

    def _warn_for_unimplemented_snapshot(self):
        if self._warned_for_missing_features:
            return

        logger.warning(
            "The connected provider does not support snapshotting. "
            "Tests will not be completely isolated."
        )
        self._warned_for_missing_features = True

    @property
    def _network_choice(self) -> str:
        # The option the user providers via --network (or the default).
        return Config.getoption("network")

    def pytest_sessionstart(self):
        """
        Called after the `Session` object has been created and before performing
        collection and entering the run test loop.

        Removes `PytestAssertRewriteWarning` warnings from the terminalreporter.
        This prevents warnings that "the `ape` library was already imported and
        so related assertions cannot be rewritten". The warning is not relevant
        for end users who are performing tests with ape.
        """
        reporter = self.config_manager.pluginmanager.get_plugin("terminalreporter")
        warnings = reporter.stats.pop("warnings", [])
        warnings = [i for i in warnings if "PytestAssertRewriteWarning" not in i.message]
        if warnings and not self.config_manager.getoption("--disable-warnings"):
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

    def pytest_sessionfinish(self):
        """
        Called after whole test run finished, right before returning the exit
        status to the system.
        """
        if self.chain_manager:
            self.chain_manager.provider.disconnect()
