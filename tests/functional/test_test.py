from pathlib import Path

import pytest

from ape.exceptions import ConfigError
from ape.pytest.config import ConfigWrapper
from ape.pytest.fixtures import FixtureManager, FixtureMap, IsolationManager, SnapshotRegistry
from ape.pytest.runners import PytestApeRunner
from ape.pytest.utils import Scope
from ape.pytest.warnings import InvalidIsolationWarning
from ape_test import ApeTestConfig
from ape_test._watch import run_with_observer


@pytest.fixture
def create_fixture_info(mocker):
    def fn(name="my_fixture", scope=Scope.FUNCTION.value, params=None, cached_result=None):
        info = mocker.MagicMock()
        info.argname = name
        info.scope = scope
        info.params = params
        info.cached_result = cached_result
        return info

    return fn


@pytest.fixture
def item(mocker, create_fixture_info):
    # foo, bar, and baz are fixtures; param0 and param1 are test-params.
    fixturenames = ["foo", "bar", "baz", "param0", "param1"]
    mock = mocker.MagicMock()
    mock.nodeid = "test_nodeid"
    mock.fixturenames = fixturenames
    mock.session._fixturemanager._arg2fixturedefs = {
        "_session_isolation": [create_fixture_info("_session_isolation", Scope.SESSION.value)],
        "_package_isolation": [create_fixture_info("_package_isolation", Scope.PACKAGE.value)],
        "foo": [create_fixture_info("foo", Scope.SESSION.value, [1, 2, 3])],
        "_module_isolation": [create_fixture_info("_module_isolation", Scope.MODULE.value)],
        "bar": [create_fixture_info("bar", Scope.MODULE.value)],
        "_class_isolation": [create_fixture_info("_class_isolation", Scope.CLASS.value)],
        "baz": [create_fixture_info("baz", Scope.CLASS.value)],
        "_function_isolation": [create_fixture_info("_function_isolation", Scope.FUNCTION.value)],
    }
    return mock


@pytest.fixture
def fixture_map(item):
    return FixtureMap.from_test_item(item)


class TestApeTestConfig:
    def test_balance_set_from_currency_str(self):
        curr_val = "10 Eth"
        data = {"balance": curr_val}
        cfg = ApeTestConfig.model_validate(data)
        actual = cfg.balance
        expected = 10_000_000_000_000_000_000  # 10 ETH in WEI
        assert actual == expected


class TestConfigWrapper:
    def test_verbosity(self, mocker):
        """
        Show it returns the same as pytest_config's.
        """
        pytest_cfg = mocker.MagicMock()
        pytest_cfg.option.verbose = False
        wrapper = ConfigWrapper(pytest_cfg)
        assert wrapper.verbosity is False

    def test_verbosity_when_no_capture(self, mocker):
        """
        Shows we enable verbose output when no-capture is set.
        """

        def get_opt(name: str):
            return "no" if name == "capture" else None

        pytest_cfg = mocker.MagicMock()
        pytest_cfg.option.verbose = False  # Start off as False
        pytest_cfg.getoption.side_effect = get_opt

        wrapper = ConfigWrapper(pytest_cfg)
        assert wrapper.verbosity is True


def test_connect_to_mainnet_by_default(mocker):
    """
    Tests the condition where mainnet is configured as the default network
    and no --network option is passed. It should avoid running the tests
    to be safe.
    """

    cfg = mocker.MagicMock()
    cfg.network = "ethereum:mainnet:node"
    runner = PytestApeRunner(
        cfg, mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock(), mocker.MagicMock()
    )
    expected = (
        "Default network is mainnet; unable to run tests on mainnet. "
        "Please specify the network using the `--network` flag or "
        "configure a different default network."
    )
    with pytest.raises(ConfigError, match=expected):
        runner._connect()


class TestFixtureManager:
    @pytest.fixture
    def fixture_manager(self, mocker):
        config = mocker.MagicMock()
        isolation = mocker.MagicMock()
        return FixtureManager(config, isolation)

    def test_ape_fixtures(self, fixture_manager):
        actual = fixture_manager._ape_fixtures
        assert "accounts" in actual
        assert "project" in actual
        assert "networks" in actual
        assert "chain" in actual

    def test_is_isolation(self, fixture_manager):
        assert fixture_manager.is_isolation("_session_isolation")
        assert fixture_manager.is_isolation("_package_isolation")
        assert fixture_manager.is_isolation("_module_isolation")
        assert fixture_manager.is_isolation("_class_isolation")
        assert fixture_manager.is_isolation("_function_isolation")
        assert not fixture_manager.is_isolation("my_custom_isolation")

    def tes_is_ape(self, fixture_manager):
        assert fixture_manager.is_ape("accounts")
        assert not fixture_manager.is_ape("acct")

    def test_is_custom(self, fixture_manager):
        assert fixture_manager.is_custom("acct")
        assert not fixture_manager.is_custom("accounts")
        assert not fixture_manager.is_custom("_module_isolation")

    def test_get_fixtures(self, fixture_manager, item):
        with pytest.raises(KeyError):
            assert fixture_manager.get_fixtures(item.nodeid) is None

        actual = fixture_manager.get_fixtures(item)
        assert isinstance(actual, FixtureMap)
        # Now, can use nodeid.
        assert fixture_manager.get_fixtures(item.nodeid) == actual

    def test_is_stateful(self, fixture_manager, item):
        fixture_manager.cache_fixtures(item)
        assert fixture_manager.is_stateful("foo") is None  # Unknown.
        fixture_manager.add_fixture_info("foo", setup_block=1, teardown_block=1)
        assert fixture_manager.is_stateful("foo") is False
        fixture_manager.add_fixture_info("bar", setup_block=1, teardown_block=2)
        assert fixture_manager.is_stateful("bar") is True

    def test_rebase(self, mocker, fixture_manager, fixture_map, create_fixture_info):
        # We must have already started our module-scope isolation.
        isolation_manager = IsolationManager(fixture_manager.config_wrapper, mocker.MagicMock())
        isolation_manager.snapshots[Scope.MODULE].identifier = "123"
        isolation_manager.snapshots[Scope.MODULE].fixtures = ["bar"]
        fixture_manager.isolation_manager = isolation_manager

        # New session fixture arrives, triggering a rebase.
        fixture_map[Scope.SESSION].append("new_session_fixture")
        fixture_map._item.fixturenames.append("new_session_fixture")
        fixture_map._item.session._fixturemanager._arg2fixturedefs["new_session_fixture"] = [
            create_fixture_info("new_session_fixture", Scope.SESSION)
        ]

        # Cache a module result so we can prove it gets cleared.
        fixture_map._item.session._fixturemanager._arg2fixturedefs["bar"][0].cached_result = "CACHE"

        # Show the module-isolation was cache and gets cleared as well.
        # NOTE: Pytest caches yield-based fixtures as a tuple, even when yields None.
        fixture_map._item.session._fixturemanager._arg2fixturedefs["_module_isolation"][
            0
        ].cached_result = (None, None, None)

        expected = (
            r"Invalid isolation; Ensure session|package|module|class scoped "
            r"fixtures run earlier\. Rebasing fixtures is costly\."
        )
        with pytest.warns(InvalidIsolationWarning, match=expected):
            fixture_manager.rebase(Scope.SESSION, fixture_map)

        # Show that module-level fixtures are invalidated, including the isolation fixture.
        for module_fixture_name in ("bar", "_module_isolation"):
            assert (
                fixture_map._item.session._fixturemanager._arg2fixturedefs[module_fixture_name][
                    0
                ].cached_result
                is None
            )
        # Show that we have reverted our module-level snapshot.
        assert isolation_manager.snapshots[Scope.MODULE].identifier is None


class TestFixtureMap:
    def test_from_test_item(self, item):
        actual = FixtureMap.from_test_item(item)
        assert actual[Scope.SESSION] == ["foo"]
        assert actual[Scope.MODULE] == ["bar"]
        assert actual[Scope.CLASS] == ["baz"]

    def test_names(self, fixture_map):
        """
        Show that we have both the initialized fixtures as well
        as the properly injected isolation fixtures. Order is
        EXTREMELY important here! It determines the order in which
        fixtures run; isolation should run before their sister fixtures.
        Function isolation is expected even when not using other function-scoped
        fixtures. Package isolation is missing because there are no
        package-scoped fixtures being used.
        """
        actual = fixture_map.names
        expected = [
            "_session_isolation",
            "foo",
            "_module_isolation",
            "bar",
            "_class_isolation",
            "baz",
            "_function_isolation",
        ]
        assert actual == expected

    def test_parameters(self, fixture_map):
        actual = fixture_map.parameters
        expected = ["param0", "param1"]
        assert actual == expected

    def test_isolation(self, fixture_map):
        actual = fixture_map.isolation
        expected = [
            "session",
            "module",
            "class",
            "function",
        ]
        assert actual == expected

    def test_parametrized(self, fixture_map):
        actual = fixture_map.parametrized
        assert "foo" in actual
        assert len(actual) == 1

    def test_get_info(self, fixture_map):
        actual = fixture_map.get_info("foo")
        assert len(actual) == 1
        assert actual[0].argname == "foo"
        assert actual[0].scope == Scope.SESSION

    def test_is_known(self, fixture_map):
        assert fixture_map.is_known("foo")
        assert not fixture_map.is_known("param0")

    def test_is_iterating(self, fixture_map):
        assert fixture_map.is_iterating("foo")
        assert not fixture_map.is_iterating("baz")

        # Iterate.
        fixture_map._item.session._fixturemanager._arg2fixturedefs["foo"][0].cached_result = (
            None,
            1,
            None,
        )
        assert fixture_map.is_iterating("foo")

        # Complete.
        fixture_map._item.session._fixturemanager._arg2fixturedefs["foo"][0].cached_result = (
            None,
            3,
            None,
        )
        assert not fixture_map.is_iterating("foo")

    def test_apply_fixturenames(self, fixture_map):
        assert fixture_map._item.fixturenames == ["foo", "bar", "baz", "param0", "param1"]
        fixture_map.apply_fixturenames()
        assert fixture_map._item.fixturenames == [
            "_session_isolation",
            "foo",
            "_module_isolation",
            "bar",
            "_class_isolation",
            "baz",
            "_function_isolation",
            "param0",
            "param1",
        ]


class TestSnapshotRegistry:
    """
    Note: Most isolation-based tests occur in `functional/test_fixtures.py`.
    """

    @pytest.fixture
    def registry(self):
        return SnapshotRegistry()

    def test_get_snapshot_id(self, registry):
        actual = registry.get_snapshot_id(Scope.SESSION)
        assert actual is None

    def test_next_snapshots(self, registry):
        actual = [x for x in registry.next_snapshots(Scope.SESSION)]
        assert actual[0].scope is Scope.PACKAGE
        assert actual[1].scope is Scope.MODULE
        assert actual[2].scope is Scope.CLASS
        assert actual[3].scope is Scope.FUNCTION


class TestIsolationManager:
    """
    Note: Most isolation-based tests occur in `functional/test_fixtures.py`.
    """

    @pytest.fixture
    def isolation_manager(self, mocker):
        config_wrapper = mocker.MagicMock()
        receipt_capture = mocker.MagicMock()
        return IsolationManager(config_wrapper, receipt_capture)

    @pytest.fixture
    def empty_snapshot_registry(self, isolation_manager):
        snapshots = isolation_manager.snapshots
        isolation_manager.snapshots = SnapshotRegistry()
        yield
        isolation_manager.snapshots = snapshots

    def test_get_snapshot(self, isolation_manager):
        actual = isolation_manager.get_snapshot(Scope.SESSION)
        assert actual.scope is Scope.SESSION

    def test_next_snapshots(self, isolation_manager):
        actual = [x for x in isolation_manager.next_snapshots(Scope.SESSION)]
        assert actual[0].scope is Scope.PACKAGE
        assert actual[1].scope is Scope.MODULE
        assert actual[2].scope is Scope.CLASS
        assert actual[3].scope is Scope.FUNCTION

    def test_isolate(
        self, isolation_manager, owner, vyper_contract_instance, empty_snapshot_registry
    ):
        """
        Low-level test simulating how pytest interacts with these yield-based
        isolation fixtures.
        """
        start_number = vyper_contract_instance.myNumber()
        session = isolation_manager.isolation(Scope.SESSION)
        module = isolation_manager.isolation(Scope.MODULE)
        function = isolation_manager.isolation(Scope.FUNCTION)

        expected_session = 10_000_000
        expected_module = 20_000_000
        expected_test = 30_000_000

        # Show we start off clear of snapshots.
        assert all(
            isolation_manager.snapshots[s].identifier is None for s in Scope
        ), "Setup failed - snapshots not empty"

        # Start session.
        next(session)
        assert isolation_manager.snapshots[Scope.SESSION].identifier is not None
        vyper_contract_instance.setNumber(expected_session, sender=owner)

        # Start module.
        next(module)
        vyper_contract_instance.setNumber(expected_module, sender=owner)

        # Start test.
        next(function)
        vyper_contract_instance.setNumber(expected_test, sender=owner)
        assert vyper_contract_instance.myNumber() == expected_test

        # End test; back to module.
        next(function, None)
        assert vyper_contract_instance.myNumber() == expected_module, "Is not back at module."

        # End module; back to session.
        assert isolation_manager.snapshots[Scope.MODULE].identifier is not None
        next(module, None)
        assert vyper_contract_instance.myNumber() == expected_session, "Is not back at session."

        # Start new module.
        module = isolation_manager.isolation(Scope.MODULE)
        next(module)
        vyper_contract_instance.setNumber(expected_module, sender=owner)

        # Start new test.
        function = isolation_manager.isolation(Scope.FUNCTION)
        next(function)
        vyper_contract_instance.setNumber(expected_test, sender=owner)
        assert vyper_contract_instance.myNumber() == expected_test

        # End test.
        next(function, None)
        assert vyper_contract_instance.myNumber() == expected_module, "(2) Is not back at module."

        # End module.
        assert isolation_manager.snapshots[Scope.MODULE].identifier is not None
        next(module, None)
        assert isolation_manager.snapshots[Scope.MODULE].identifier is None
        assert vyper_contract_instance.myNumber() == expected_session, "(2) Is not back at session."

        # End session.
        next(session, None)
        assert vyper_contract_instance.myNumber() == start_number, "(2) Is not back pre-session."


def test_watch(mocker):
    mock_event_handler = mocker.MagicMock()
    event_handler_patch = mocker.patch("ape_test._watch._create_event_handler")
    event_handler_patch.return_value = mock_event_handler

    mock_observer = mocker.MagicMock()
    observer_patch = mocker.patch("ape_test._watch._create_observer")
    observer_patch.return_value = mock_observer

    run_subprocess_patch = mocker.patch("ape_test._watch.run_subprocess")
    run_main_loop_patch = mocker.patch("ape_test._watch._run_main_loop")
    run_main_loop_patch.side_effect = SystemExit  # Avoid infinite loop.

    # Only passing `-s` so we have an extra arg to test.
    with pytest.raises(SystemExit):
        run_with_observer((Path("contracts"),), 0.1, "-s")

    # The observer started, then the main runner exits, and the observer stops + joins.
    assert mock_observer.start.call_count == 1
    assert mock_observer.stop.call_count == 1
    assert mock_observer.join.call_count == 1

    # NOTE: We had a bug once where the args it received were not strings.
    #   (wasn't deconstructing), so this check is important.
    run_subprocess_patch.assert_called_once_with(["ape", "test", "-s"])
