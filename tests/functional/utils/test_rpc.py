import pytest

from ape.utils.rpc import RPCHeaders, stream_response


def test_stream_response(mocker):
    expected = b"".join(bytes([i]) * 128 for i in range(256))
    response = mocker.MagicMock()
    response.headers = {"content-length": str(len(expected))}
    response.iter_content.return_value = [expected[:1024], expected[1024:]]

    get = mocker.patch("ape.utils.rpc.requests.get", return_value=response)

    actual = stream_response("https://example.com/package.zip")

    get.assert_called_once_with("https://example.com/package.zip", stream=True)
    response.raise_for_status.assert_called_once_with()
    response.iter_content.assert_called_once_with(chunk_size=2**16)
    assert actual == expected


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
