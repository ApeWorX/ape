import pytest

from ape.utils.rpc import RPCHeaders


class TestRPCHeaders:
    @pytest.fixture
    def headers(self):
        return RPCHeaders()

    @pytest.mark.parametrize("key", ("Content-Type", "CONTENT-TYPE"))
    def test_setitem_key_case_insensitive(self, key, headers):
        headers[key] = "application/javascript"
        headers[key.lower()] = "application/json"
        assert headers[key] == "application/json"
        assert headers[key.lower()] == "application/json"

    def test_setitem_user_agent_does_not_add_twice(self, headers):
        expected = "test-user-agent/1.0"
        headers["User-Agent"] = expected
        # Add again. It should not add twice.
        headers["User-Agent"] = expected
        assert headers["User-Agent"] == expected

    def test_setitem_user_agent_appends(self, headers):
        headers["User-Agent"] = "test0/1.0"
        headers["User-Agent"] = "test1/2.0"
        assert headers["User-Agent"] == "test0/1.0 test1/2.0"

    def test_setitem_user_agent_parts_exist(self, headers):
        """
        Tests the case when user-agents share a sub-set
        of each other, that it does not duplicate.
        """
        headers["User-Agent"] = "test0/1.0"
        # The beginning of the user-agent is already present.
        # It shouldn't add the full thing.
        headers["User-Agent"] = "test0/1.0 test1/2.0"
        assert headers["User-Agent"] == "test0/1.0 test1/2.0"
        # unexpected = "test0/1.0 test0/1.0 test1/2.0"

    @pytest.mark.parametrize("key", ("user-agent", "User-Agent", "USER-AGENT"))
    def test_contains_user_agent(self, key, headers):
        headers["User-Agent"] = "test0/1.0"
        assert key in headers
