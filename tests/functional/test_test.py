import pytest

from ape.pytest.fixtures import FixtureManager, FixtureMap, IsolationManager, SnapshotRegistry
from ape.pytest.utils import Scope
from ape.pytest.warnings import InvalidIsolationWarning
from ape_test import ApeTestConfig


@pytest.fixture
def create_fixture_info(mocker):
    def fn(name="my_fixture", scope=Scope.FUNCTION.value, params=None, cached_result=None):
        info = mocker.MagicMock()
        info.name = name
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
        "foo": [create_fixture_info("foo", Scope.SESSION.value, [1, 2, 3])],
        "bar": [create_fixture_info("bar", Scope.MODULE.value)],
        "baz": [create_fixture_info("baz", Scope.CLASS.value)],
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
        fixture_manager.add_fixture_info("foo", teardown_block=2)
        assert fixture_manager.is_stateful("foo") is True

    def test_rebase(self, mocker, fixture_manager, fixture_map, create_fixture_info):
        # We must have already started our module-scope isolation.
        isolation_manager = IsolationManager(fixture_manager.config_wrapper, mocker.MagicMock())
        isolation_manager.snapshots[Scope.MODULE].identifier = "123"
        fixture_manager.isolation_manager = isolation_manager

        # New session fixture arrives, triggering a rebase.
        fixture_map[Scope.SESSION].append("new_session_fixture")
        fixture_map._item.fixturenames.append("new_session_fixture")
        fixture_map._item.session._fixturemanager._arg2fixturedefs["new_session_fixture"] = [
            create_fixture_info("new_session_fixture", Scope.SESSION)
        ]

        expected = (
            r"Invalid isolation; Ensure session|package|module|class scoped "
            r"fixtures run earlier\. Rebasing fixtures is costly\."
        )
        with pytest.warns(InvalidIsolationWarning, match=expected):
            fixture_manager.rebase(Scope.SESSION, fixture_map)


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
        assert actual[0].name == "foo"
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
    @pytest.fixture
    def isolation_manager(self, mocker):
        config_wrapper = mocker.MagicMock()
        receipt_capture = mocker.MagicMock()
        return IsolationManager(config_wrapper, receipt_capture)

    def test_get_snapshot(self, isolation_manager):
        actual = isolation_manager.get_snapshot(Scope.SESSION)
        # Empty.
        assert actual.scope is Scope.SESSION
        assert actual.identifier is None
        assert actual.fixtures == []

    def test_next_snapshots(self, isolation_manager):
        actual = [x for x in isolation_manager.next_snapshots(Scope.SESSION)]
        assert actual[0].scope is Scope.PACKAGE
        assert actual[1].scope is Scope.MODULE
        assert actual[2].scope is Scope.CLASS
        assert actual[3].scope is Scope.FUNCTION
