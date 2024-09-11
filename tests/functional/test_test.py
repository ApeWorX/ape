from ape.pytest.runners import _insert_isolation_fixtures
from ape_test import ApeTestConfig


class TestApeTestConfig:
    def test_balance_set_from_currency_str(self):
        curr_val = "10 Eth"
        data = {"balance": curr_val}
        cfg = ApeTestConfig.model_validate(data)
        actual = cfg.balance
        expected = 10_000_000_000_000_000_000  # 10 ETH in WEI
        assert actual == expected


def test_insert_isolation_fixtures(mocker):
    mock_item = mocker.MagicMock()

    def _create_fixture_entry(name: str, scope: str):
        mock_fixture = mocker.MagicMock()
        mock_fixture.scope = scope
        mock_fixture.name = name
        return mock_fixture

    fixtures = {
        "fixture_at_function": [_create_fixture_entry("fixture_at_function", "function")],
        "fixture_at_session": [_create_fixture_entry("fixture_at_session", "session")],
        "fixture_at_module": [_create_fixture_entry("fixture_at_module", "module")],
        "fixture_at_class": [_create_fixture_entry("fixture_at_class", "class")],
        "other_random_fixture": [_create_fixture_entry("other_random_fixture", "function")],
        # Show case where fixture is already present.
        "_class_isolation": [_create_fixture_entry("_class_isolation", "class")],
    }

    mock_item.session._fixturemanager._arg2fixturedefs = fixtures
    mock_item.fixturenames = [*list(fixtures.keys()), "otheriteminnames"]
    _insert_isolation_fixtures(mock_item)
    actual = sorted(mock_item.fixturenames)
    expected = [
        "_class_isolation",
        "_function_isolation",
        "_module_isolation",
        "_session_isolation",
        "fixture_at_class",
        "fixture_at_function",
        "fixture_at_module",
        "fixture_at_session",
        "other_random_fixture",
        "otheriteminnames",
    ]
    assert actual == expected
