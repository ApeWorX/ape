import inspect
import re
from collections import defaultdict
from collections.abc import Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from fnmatch import fnmatch
from functools import cached_property, singledispatchmethod
from typing import TYPE_CHECKING, ClassVar, Optional

import pytest
from eth_utils import to_hex

from ape.exceptions import BlockNotFoundError, ChainError, ProviderNotConnectedError
from ape.logging import logger
from ape.pytest.utils import Scope
from ape.utils.basemodel import ManagerAccessMixin
from ape.utils.rpc import allow_disconnected

if TYPE_CHECKING:
    from ape.api.accounts import TestAccountAPI
    from ape.api.transactions import ReceiptAPI
    from ape.managers.chain import ChainManager
    from ape.managers.networks import NetworkManager
    from ape.managers.project import ProjectManager
    from ape.pytest.config import ConfigWrapper
    from ape.types.vm import SnapshotID


@dataclass()
class FixtureRebase:
    return_scope: Scope
    invalid_fixtures: dict[Scope, list[str]]


class FixtureManager(ManagerAccessMixin):
    _builtin_fixtures: ClassVar[list] = []
    _stateful_fixtures_cache: ClassVar[dict[str, bool]] = {}
    _ISOLATION_FIXTURE_REGEX = re.compile(r"_(session|package|module|class|function)_isolation")

    def __init__(self, config_wrapper: "ConfigWrapper", isolation_manager: "IsolationManager"):
        self.config_wrapper = config_wrapper
        self.isolation_manager = isolation_manager
        self._nodeid_to_fixture_map: dict[str, "FixtureMap"] = {}
        self._fixture_name_to_info: dict[str, dict] = {}

    @classmethod
    def set_builtins(cls, fixture_map: "FixtureMap"):
        cls._builtin_fixtures = [
            n
            for n, defs in fixture_map._arg2fixturedefs.items()
            if any("pytest" in fixture.func.__module__ for fixture in defs)
        ]

    @cached_property
    def _ape_fixtures(self) -> tuple[str, ...]:
        return tuple(
            [
                n
                for n, itm in inspect.getmembers(PytestApeFixtures)
                if callable(itm) and not n.startswith("_")
            ]
        )

    @property
    def builtin_fixtures(self) -> list[str]:
        return self._builtin_fixtures

    def is_builtin(self, name: str) -> bool:
        return name in self.builtin_fixtures

    @classmethod
    def is_isolation(cls, name: str) -> bool:
        return bool(re.match(cls._ISOLATION_FIXTURE_REGEX, name))

    def is_ape(self, name: str) -> bool:
        return name in self._ape_fixtures

    def is_custom(self, name) -> bool:
        return not self.is_builtin(name) and not self.is_ape(name) and not self.is_isolation(name)

    def get_fixtures(self, item) -> "FixtureMap":
        if isinstance(item, str):
            # Cached map referenced where only have nodeid.
            if fixture_map := self._get_cached_fixtures(item):
                return fixture_map

            raise KeyError(f"No item found with nodeid '{item}'.")

        elif fixture_map := self._get_cached_fixtures(item.nodeid):
            # Cached map.
            return fixture_map

        return self.cache_fixtures(item)

    def cache_fixtures(self, item) -> "FixtureMap":
        fixture_map = FixtureMap.from_test_item(item)
        if not FixtureManager._builtin_fixtures:
            FixtureManager.set_builtins(fixture_map)

        self._nodeid_to_fixture_map[item.nodeid] = fixture_map
        for scope, fixture_set in fixture_map.items():
            for fixture_name in fixture_set:
                if fixture_name not in self._fixture_name_to_info:
                    self._fixture_name_to_info[fixture_name] = {"scope": scope}

        return fixture_map

    def get_fixture_scope(self, fixture_name: str) -> Optional[Scope]:
        return self._fixture_name_to_info.get(fixture_name, {}).get("scope")

    def is_stateful(self, name: str) -> Optional[bool]:
        if name in self._stateful_fixtures_cache:
            # Used `@ape.fixture(chain_isolation=<bool>)
            # Or we already calculated.
            return self._stateful_fixtures_cache[name]

        try:
            is_auto_mine = self.provider.auto_mine
        except (NotImplementedError, ProviderNotConnectedError):
            # Assume it's on since it can't be turned off.
            is_auto_mine = True

        if not is_auto_mine:
            # When auto-mine is disabled, it's unknown.
            return None

        elif not (info := self._fixture_name_to_info.get(name)):
            # Statefulness not yet tracked. Unknown.
            return None

        setup_block = info.get("setup_block")
        teardown_block = info.get("teardown_block")
        if setup_block is None or teardown_block is None:
            # Blocks no set. Unknown.
            return None

        # If the two are not equal, state has changed.
        is_stateful = setup_block != teardown_block
        self._stateful_fixtures_cache[name] = is_stateful

        # Clear out blocks since they are no longer needed.
        self._fixture_name_to_info[name] = {
            k: v
            for k, v in self._fixture_name_to_info[name].items()
            if k not in ("setup_block", "teardown_block")
        }

        return is_stateful

    def add_fixture_info(self, name: str, **info):
        if name not in self._fixture_name_to_info:
            self._fixture_name_to_info[name] = info
        else:
            self._fixture_name_to_info[name] = {
                **self._fixture_name_to_info[name],
                **info,
            }

    def _get_cached_fixtures(self, nodeid: str) -> Optional["FixtureMap"]:
        return self._nodeid_to_fixture_map.get(nodeid)

    def rebase(self, scope: Scope, fixtures: "FixtureMap"):
        if not (rebase := self._get_rebase(scope)):
            # Rebase avoided: nothing would change.
            return

        from ape.pytest.warnings import warn_invalid_isolation

        warn_invalid_isolation()
        self.isolation_manager.restore(rebase.return_scope)

        # Invalidate fixtures by clearing out their cached result.
        invalidated = []
        for invalid_scope, invalid_fixture_ls in rebase.invalid_fixtures.items():
            for invalid_fixture in invalid_fixture_ls:
                info_ls = fixtures.get_info(invalid_fixture)
                for info in info_ls:
                    if self.is_stateful(info.argname) is False:
                        # It has been determined that this fixture is not stateful.
                        continue

                    info.cached_result = None
                    invalidated.append(info.argname)

            # Also, invalidate the corresponding isolation fixture.
            if invalid_isolation_fixture_ls := fixtures.get_info(
                invalid_scope.isolation_fixturename
            ):
                for invalid_isolation_fixture in invalid_isolation_fixture_ls:
                    invalid_isolation_fixture.cached_result = None
                    invalidated.append(invalid_isolation_fixture.argname)

            if invalidated and self.config_wrapper.verbosity:
                log = "rebase"
                if rebase.return_scope is not None:
                    log = f"{log} scope={rebase.return_scope}"

    def _get_rebase(self, scope: Scope) -> Optional[FixtureRebase]:
        # Check for fixtures that are now invalid. For example, imagine a session
        # fixture comes into play after the module snapshot has been set.
        # Once we restore the module's state and move to the next module,
        # that session fixture will no longer exist. To remedy this situation,
        # we invalidate the lower-scoped fixtures and re-snapshot everything.
        scope_to_revert = None
        invalids = defaultdict(list)
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

            # All stateful fixtures downward are "below scope"
            fixtures = [f for f in next_snapshot.fixtures if self.is_stateful(f) is not False]
            invalids[next_snapshot.scope].extend(fixtures)

        invalids_dict = dict(invalids)
        return (
            FixtureRebase(return_scope=scope_to_revert, invalid_fixtures=invalids_dict)
            if scope_to_revert is not None and any(len(ls) > 0 for ls in invalids_dict.values())
            else None
        )


class FixtureMap(dict[Scope, list[str]]):
    def __init__(self, item):
        self._item = item
        self._parametrized_names: Optional[list[str]] = None
        super().__init__(
            {
                Scope.SESSION: [],
                Scope.PACKAGE: [],
                Scope.MODULE: [],
                Scope.CLASS: [],
                Scope.FUNCTION: [],
            }
        )

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} {self._item.nodeid}>"

    @classmethod
    def from_test_item(cls, item) -> "FixtureMap":
        obj = cls(item)
        for name, info_ls in obj._arg2fixturedefs.items():
            if not info_ls or name not in item.fixturenames:
                continue

            for info in info_ls:
                obj[info.scope].append(name)

        return obj

    @property
    def names(self) -> list[str]:
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

    @property
    def parameters(self) -> list[str]:
        """
        Test-parameters (not fixtures!)
        """
        return [n for n in self._item.fixturenames if n not in self._arg2fixturedefs]

    @property
    def isolation(self) -> list[str]:
        return [n.lstrip("_").split("_")[0] for n in self.names if FixtureManager.is_isolation(n)]

    @property
    def parametrized(self) -> dict[str, list]:
        if self._parametrized_names is not None:
            # We have already done this.
            return {
                n: ls for n, ls in self._arg2fixturedefs.items() if n in self._parametrized_names
            }

        # Calculating for first time.
        self._parametrized_names = []
        result: dict[str, list] = {}
        for name, info_ls in self._arg2fixturedefs.items():
            if name not in self._item.fixturenames or not any(info.params for info in info_ls):
                continue

            self._parametrized_names.append(name)
            result[name] = info_ls

        return result

    @property
    def _arg2fixturedefs(self) -> Mapping:
        return self._item.session._fixturemanager._arg2fixturedefs

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
        # NOTE: Not using singledispatchmethod because it requires
        #  types at runtime.
        if isinstance(key, Scope):
            return self.__getitem_scope(key)
        elif isinstance(key, str):
            return self.__getitem_str(key)
        elif isinstance(key, int):
            return self.__getitem_int(key)

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

    def get_info(self, name: str) -> list:
        """
        Get fixture info.

        Args:
            name (str):

        Returns:
            list of info
        """
        if name not in self._arg2fixturedefs:
            return []

        return self._arg2fixturedefs[name]

    def is_known(self, name: str) -> bool:
        """
        True when fixture-info is known for the given fixture name.
        """
        return name in self._arg2fixturedefs

    def is_iterating(self, name: str) -> bool:
        """
        True when is a non-function scoped parametrized fixture that hasn't
        fully iterated.
        """
        if name not in self.parametrized:
            return False

        elif not (info_ls := self.get_info(name)):
            return False

        for info in info_ls:
            if not info.params:
                continue

            if not info.cached_result:
                return True  # First iteration

            elif len(info.cached_result) < 2:
                continue  # ?

            last_param_ran = info.cached_result[1]
            last_param = info.params[-1]
            if last_param_ran != last_param:
                return True  # Is iterating.

        return False

    def apply_fixturenames(self):
        """
        Set the fixturenames on the test item in the order they should be used.
        Carefully ignore non-fixtures, such as keys from parametrized tests.
        """
        self._item.fixturenames = [*self.names, *self.parameters]


class PytestApeFixtures(ManagerAccessMixin):
    # NOTE: Avoid including links, markdown, or rst in method-docs
    # for fixtures, as they are used in output from the command
    # `ape test -q --fixture` (`pytest -q --fixture`).

    def __init__(self, config_wrapper: "ConfigWrapper", isolation_manager: "IsolationManager"):
        self.config_wrapper = config_wrapper
        self.isolation_manager = isolation_manager

    @pytest.fixture(scope="session")
    def accounts(self) -> list["TestAccountAPI"]:
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

    @pytest.fixture(scope="session")
    def chain(self) -> "ChainManager":
        """
        Manipulate the blockchain, such as mine or change the pending timestamp.
        """
        return self.chain_manager

    @pytest.fixture(scope="session")
    def networks(self) -> "NetworkManager":
        """
        Connect to other networks in your tests.
        """
        return self.network_manager

    @pytest.fixture(scope="session")
    def project(self) -> "ProjectManager":
        """
        Access contract types and dependencies.
        """
        return self.local_project

    @pytest.fixture(scope="session")
    def Contract(self):
        """
        Instantiate a reference to an on-chain contract
        using its address (same as ``ape.Contract``).
        """
        return self.chain_manager.contracts.instance_at

    @pytest.fixture(scope="session")
    def _session_isolation(self) -> Iterator[None]:
        yield from self.isolation_manager.isolation(Scope.SESSION)

    @pytest.fixture(scope="package")
    def _package_isolation(self) -> Iterator[None]:
        yield from self.isolation_manager.isolation(Scope.PACKAGE)

    @pytest.fixture(scope="module")
    def _module_isolation(self) -> Iterator[None]:
        yield from self.isolation_manager.isolation(Scope.MODULE)

    @pytest.fixture(scope="class")
    def _class_isolation(self) -> Iterator[None]:
        yield from self.isolation_manager.isolation(Scope.CLASS)

    @pytest.fixture(scope="function")
    def _function_isolation(self) -> Iterator[None]:
        yield from self.isolation_manager.isolation(Scope.FUNCTION)


@dataclass
class Snapshot:
    """
    All the data necessary for accurately supporting isolation.
    """

    scope: Scope
    """Corresponds to fixture scope."""

    identifier: Optional["SnapshotID"] = None
    """Snapshot ID taken before the peer-fixtures in the same scope."""

    fixtures: list = field(default_factory=list)
    """All peer fixtures, tracked so we know when new ones are added."""

    def append_fixtures(self, fixtures: Iterable[str]):
        for fixture in fixtures:
            if fixture in self.fixtures:
                continue

            self.fixtures.append(fixture)


class SnapshotRegistry(dict[Scope, Snapshot]):
    def __init__(self):
        super().__init__(
            {
                Scope.SESSION: Snapshot(Scope.SESSION),
                Scope.PACKAGE: Snapshot(Scope.PACKAGE),
                Scope.MODULE: Snapshot(Scope.MODULE),
                Scope.CLASS: Snapshot(Scope.CLASS),
                Scope.FUNCTION: Snapshot(Scope.FUNCTION),
            }
        )

    def get_snapshot_id(self, scope: Scope) -> Optional["SnapshotID"]:
        return self[scope].identifier

    def set_snapshot_id(self, scope: Scope, snapshot_id: "SnapshotID"):
        self[scope].identifier = snapshot_id

    def clear_snapshot_id(self, scope: Scope):
        self[scope].identifier = None

    def next_snapshots(self, scope: Scope) -> Iterator[Snapshot]:
        for scope_value in range(scope + 1, Scope.FUNCTION + 1):
            yield self[scope_value]  # type: ignore

    def extend_fixtures(self, scope: Scope, fixtures: Iterable[str]):
        self[scope].fixtures.extend(fixtures)


class IsolationManager(ManagerAccessMixin):
    supported: bool = True
    snapshots: SnapshotRegistry = SnapshotRegistry()

    def __init__(
        self,
        config_wrapper: "ConfigWrapper",
        receipt_capture: "ReceiptCapture",
        chain_snapshots: Optional[dict] = None,
    ):
        self.config_wrapper = config_wrapper
        self.receipt_capture = receipt_capture
        self._chain_snapshots = chain_snapshots

    @cached_property
    def _track_transactions(self) -> bool:
        return (
            self.network_manager.provider is not None
            and self.provider.is_connected
            and (self.config_wrapper.track_gas or self.config_wrapper.track_coverage)
        )

    @property
    def chain_snapshots(self) -> dict:
        return self._chain_snapshots or self.chain_manager._snapshots

    def get_snapshot(self, scope: Scope) -> Snapshot:
        return self.snapshots[scope]

    def extend_fixtures(self, scope: Scope, fixtures: Iterable[str]):
        self.snapshots.extend_fixtures(scope, fixtures)

    def next_snapshots(self, scope: Scope) -> Iterator[Snapshot]:
        yield from self.snapshots.next_snapshots(scope)

    def isolation(self, scope: Scope) -> Iterator[None]:
        """
        Isolation logic used to implement isolation fixtures for each pytest scope.
        When tracing support is available, will also assist in capturing receipts.
        """
        self.set_snapshot(scope)
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
        if not self.supported:
            return

        self.restore(scope)

    def set_snapshot(self, scope: Scope):
        # Also can be used to re-set snapshot.
        if not self.supported:
            return

        try:
            snapshot_id = self.take_snapshot()
        except Exception:
            self.supported = False
        else:
            if snapshot_id is not None:
                self.snapshots.set_snapshot_id(scope, snapshot_id)

    @allow_disconnected
    def take_snapshot(self) -> Optional["SnapshotID"]:
        try:
            return self.chain_manager.snapshot()
        except NotImplementedError:
            logger.warning(
                "The connected provider does not support snapshotting. "
                "Tests will not be completely isolated."
            )
            # To avoid trying again
            self.supported = False

        return None

    @allow_disconnected
    def restore(self, scope: Scope):
        snapshot_id = self.snapshots.get_snapshot_id(scope)
        if snapshot_id is None:
            return

        elif snapshot_id not in self.chain_snapshots[self.provider.chain_id]:
            # Still clear out.
            self.snapshots.clear_snapshot_id(scope)
            return

        try:
            self._restore(snapshot_id)
        except NotImplementedError:
            logger.warning(
                "The connected provider does not support snapshotting. "
                "Tests will not be completely isolated."
            )
            # To avoid trying again
            self.supported = False

        self.snapshots.clear_snapshot_id(scope)

    def _restore(self, snapshot_id: "SnapshotID"):
        self.chain_manager.restore(snapshot_id)


class ReceiptCapture(ManagerAccessMixin):
    receipt_map: dict[str, dict[str, "ReceiptAPI"]] = {}
    enter_blocks: list[int] = []

    def __init__(self, config_wrapper: "ConfigWrapper"):
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


def fixture(chain_isolation: Optional[bool], **kwargs):
    """
    A thin-wrapper around ``@pytest.fixture`` with extra capabilities.
    Set ``chain_isolation`` to ``False`` to signal to Ape that this fixture's
    cached result is the same regardless of block number and it does not
    need to be invalidated during times or pytest-scoped based chain rebasing.

    Usage example::

        import ape
        from ape_tokens import tokens

        @ape.fixture(scope="session", chain_isolation=False, params=("WETH", "DAI", "BAT"))
        def token_addresses(request):
            return tokens[request].address

    """

    def decorator(fixture_function):
        if chain_isolation is not None:
            name = kwargs.get("name", fixture_function.__name__)
            FixtureManager._stateful_fixtures_cache[name] = chain_isolation

        return pytest.fixture(fixture_function, **kwargs)

    return decorator
