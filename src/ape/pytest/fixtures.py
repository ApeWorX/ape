import inspect
from collections.abc import Iterable, Iterator
from dataclasses import dataclass, field
from fnmatch import fnmatch
from functools import cached_property
from typing import Optional

import pytest
from eth_utils import to_hex

from ape.api.accounts import TestAccountAPI
from ape.api.transactions import ReceiptAPI
from ape.exceptions import BlockNotFoundError, ChainError
from ape.logging import logger
from ape.managers.chain import ChainManager
from ape.managers.networks import NetworkManager
from ape.managers.project import ProjectManager
from ape.pytest.config import ConfigWrapper
from ape.pytest.utils import Scope
from ape.types import SnapshotID
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.rpc import allow_disconnected


class PytestApeFixtures(ManagerAccessMixin):
    # NOTE: Avoid including links, markdown, or rst in method-docs
    # for fixtures, as they are used in output from the command
    # `ape test -q --fixture` (`pytest -q --fixture`).

    def __init__(self, config_wrapper: ConfigWrapper, isolation_manager: "IsolationManager"):
        self.config_wrapper = config_wrapper
        self.isolation_manager = isolation_manager

    @pytest.fixture(scope=Scope.SESSION.value)
    def accounts(self) -> list[TestAccountAPI]:
        """
        A collection of pre-funded accounts.
        """
        return self.account_manager.test_accounts

    @pytest.fixture(scope="session")
    def compilers(self):
        """
        Access compiler manager directly.
        """
        return self.compiler_manager

    @pytest.fixture(scope=Scope.SESSION.value)
    def chain(self) -> ChainManager:
        """
        Manipulate the blockchain, such as mine or change the pending timestamp.
        """
        return self.chain_manager

    @pytest.fixture(scope=Scope.SESSION.value)
    def networks(self) -> NetworkManager:
        """
        Connect to other networks in your tests.
        """
        return self.network_manager

    @pytest.fixture(scope=Scope.SESSION.value)
    def project(self) -> ProjectManager:
        """
        Access contract types and dependencies.
        """
        return self.local_project

    @pytest.fixture(scope=Scope.SESSION.value)
    def Contract(self):
        """
        Instantiate a reference to an on-chain contract
        using its address (same as ``ape.Contract``).
        """
        return self.chain_manager.contracts.instance_at

    # isolation fixtures
    @pytest.fixture(scope=Scope.SESSION.value)
    def _session_isolation(self) -> Iterator[None]:
        yield from self.isolation_manager.isolation(Scope.SESSION)

    @pytest.fixture(scope=Scope.PACKAGE.value)
    def _package_isolation(self) -> Iterator[None]:
        yield from self.isolation_manager.isolation(Scope.PACKAGE)

    @pytest.fixture(scope=Scope.MODULE.value)
    def _module_isolation(self) -> Iterator[None]:
        yield from self.isolation_manager.isolation(Scope.MODULE)

    @pytest.fixture(scope=Scope.CLASS.value)
    def _class_isolation(self) -> Iterator[None]:
        yield from self.isolation_manager.isolation(Scope.CLASS)

    @pytest.fixture(scope=Scope.FUNCTION.value)
    def _function_isolation(self) -> Iterator[None]:
        yield from self.isolation_manager.isolation(Scope.FUNCTION)


@dataclass
class Snapshot:
    scope: "Scope"  # Assuming 'Scope' is defined elsewhere
    identifier: Optional[str] = None
    fixtures: list = field(default_factory=list)


def _get_lower_scopes(scope: Scope) -> tuple[Scope, ...]:
    if scope is Scope.SESSION:
        return (Scope.FUNCTION, Scope.CLASS, Scope.MODULE, Scope.PACKAGE)
    elif scope is Scope.PACKAGE:
        return (Scope.FUNCTION, Scope.CLASS, Scope.MODULE)
    elif scope is Scope.MODULE:
        return (Scope.FUNCTION, Scope.CLASS)
    elif scope is Scope.CLASS:
        return (Scope.FUNCTION,)

    return ()


class IsolationManager(ManagerAccessMixin):
    INVALID_KEY = "__invalid_snapshot__"

    _supported: bool = True
    _snapshot_registry: dict[Scope, Snapshot] = {
        Scope.SESSION: Snapshot(Scope.SESSION),
        Scope.PACKAGE: Snapshot(Scope.PACKAGE),
        Scope.MODULE: Snapshot(Scope.MODULE),
        Scope.CLASS: Snapshot(Scope.CLASS),
        Scope.FUNCTION: Snapshot(Scope.FUNCTION),
    }

    def __init__(self, config_wrapper: ConfigWrapper, receipt_capture: "ReceiptCapture"):
        self.config_wrapper = config_wrapper
        self.receipt_capture = receipt_capture

    @cached_property
    def builtin_ape_fixtures(self) -> tuple[str, ...]:
        return tuple(
            [
                n
                for n, itm in inspect.getmembers(PytestApeFixtures)
                if callable(itm) and not n.startswith("_")
            ]
        )

    @cached_property
    def _track_transactions(self) -> bool:
        return (
            self.network_manager.provider is not None
            and self.provider.is_connected
            and (self.config_wrapper.track_gas or self.config_wrapper.track_coverage)
        )

    def update_fixtures(self, scope: Scope, fixtures: Iterable[str]):
        snapshot = self._snapshot_registry[scope]
        if not (
            new_fixtures := [
                p
                for p in fixtures
                if p not in snapshot.fixtures and p not in self.builtin_ape_fixtures
            ]
        ):
            return

        # If the snapshot is already set, we have to invalidate it.
        # We need to replace the snapshot with one that happens after
        # the new fixtures.
        # if snapshot is not None:
        #     breakpoint()
        #     self._snapshot_registry[scope].identifier = self.INVALID_KEY

        # Add or update peer-fixtures.
        self._snapshot_registry[scope].fixtures.extend(new_fixtures)

    def isolation(self, scope: Scope) -> Iterator[None]:
        """
        Isolation logic used to implement isolation fixtures for each pytest scope.
        When tracing support is available, will also assist in capturing receipts.
        """
        self._set_snapshot(scope)
        if self._track_transactions:
            did_yield = False
            try:
                with self.receipt_capture:
                    yield
                    did_yield = True

            except BlockNotFoundError:
                if not did_yield:
                    # Prevent double yielding.
                    yield
        else:
            yield

        # NOTE: self._supported may have gotten set to False
        #   someplace else _after_ snapshotting succeeded.
        if not self._supported:
            return

        self._restore(scope)

    def _set_snapshot(self, scope: Scope):
        # Also can be used to re-set snapshot.
        if not self._supported:
            return

        # Here is something tricky: If a snapshot exists
        # already at a lower-level, we must use that one.
        # Like if a session comes in _after_ a module, have
        # the session just use the module.
        # Else, it falls apart.
        snapshot_id = None
        if scope is not Scope.FUNCTION:
            lower_scopes = _get_lower_scopes(scope)
            for lower_scope in lower_scopes:
                snapshot = self._snapshot_registry[lower_scope]
                if snapshot.identifier is not None:
                    snapshot_id = snapshot.identifier
                    break

            if snapshot_id is not None:
                # Clear out others
                for lower_scope in lower_scopes:
                    snapshot = self._snapshot_registry[lower_scope]
                    snapshot.identifier = None

        if snapshot_id is None:
            try:
                snapshot_id = self._take_snapshot()
            except Exception:
                self._supported = False

        if snapshot_id is not None:
            self._snapshot_registry[scope].identifier = snapshot_id

    @allow_disconnected
    def _take_snapshot(self) -> Optional[SnapshotID]:
        try:
            return self.chain_manager.snapshot()
        except NotImplementedError:
            logger.warning(
                "The connected provider does not support snapshotting. "
                "Tests will not be completely isolated."
            )
            # To avoid trying again
            self._supported = False

        return None

    @allow_disconnected
    def _restore(self, scope: Scope):
        snapshot_id = self._snapshot_registry[scope].identifier
        if snapshot_id is None:
            return

        elif snapshot_id not in self.chain_manager._snapshots or snapshot_id == self.INVALID_KEY:
            # Still clear out.
            self._snapshot_registry[scope].identifier = None
            return

        try:
            self.chain_manager.restore(snapshot_id)
        except NotImplementedError:
            logger.warning(
                "The connected provider does not support snapshotting. "
                "Tests will not be completely isolated."
            )
            # To avoid trying again
            self._supported = False

        self._snapshot_registry[scope].identifier = None

        # If we are reverting to a session-state, there is no
        # reason to revert back to a function state (if one exists).
        # and so forth.
        lower_scopes = _get_lower_scopes(scope)
        for lower_scope in lower_scopes:
            self._snapshot_registry[lower_scope].identifier = None


class ReceiptCapture(ManagerAccessMixin):
    receipt_map: dict[str, dict[str, ReceiptAPI]] = {}
    enter_blocks: list[int] = []

    def __init__(self, config_wrapper: ConfigWrapper):
        self.config_wrapper = config_wrapper

    def __enter__(self):
        block_number = self._get_block_number()
        if block_number is not None:
            self.enter_blocks.append(block_number)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if not self.enter_blocks:
            return

        start_block = self.enter_blocks.pop()
        stop_block = self._get_block_number()
        if stop_block is None or start_block > stop_block:
            return

        self.capture_range(start_block, stop_block)

    def capture_range(self, start_block: int, stop_block: int):
        blocks = self.chain_manager.blocks.range(start_block, stop_block + 1)
        transactions = [t for b in blocks for t in b.transactions]

        for txn in transactions:
            try:
                txn_hash = to_hex(txn.txn_hash)
            except Exception:
                # Might have been from an impersonated account.
                # Those txns need to be added separately, same as tracing calls.
                # Likely, it was already accounted before this point.
                continue

            self.capture(txn_hash)

    def capture(self, transaction_hash: str):
        try:
            receipt = self.chain_manager.history[transaction_hash]
        except ChainError:
            return

        if not receipt:
            return

        elif not (contract_address := (receipt.receiver or receipt.contract_address)):
            return

        elif not (contract_type := self.chain_manager.contracts.get(contract_address)):
            # Not an invoke-transaction or a known address
            return

        elif not (source_id := (contract_type.source_id or None)):
            # Not a local or known contract type.
            return

        elif source_id not in self.receipt_map:
            self.receipt_map[source_id] = {}

        if transaction_hash in self.receipt_map[source_id]:
            # Transaction already known.
            return

        self.receipt_map[source_id][transaction_hash] = receipt
        if self.config_wrapper.track_gas:
            receipt.track_gas()

        if self.config_wrapper.track_coverage:
            receipt.track_coverage()

    def clear(self):
        self.receipt_map = {}
        self.enter_blocks = []

    @allow_disconnected
    def _get_block_number(self) -> Optional[int]:
        return self.provider.get_block("latest").number

    def _exclude_from_gas_report(
        self, contract_name: str, method_name: Optional[str] = None
    ) -> bool:
        """
        Helper method to determine if a certain contract / method combination should be
        excluded from the gas report.
        """
        for exclusion in self.config_wrapper.gas_exclusions:
            # Default to looking at all contracts
            contract_pattern = exclusion.contract_name
            if not fnmatch(contract_name, contract_pattern) or not method_name:
                continue

            method_pattern = exclusion.method_name
            if not method_pattern or fnmatch(method_name, method_pattern):
                return True

        return False
