import tempfile

import pytest
from github import UnknownObjectException

from ape.utils.github import GithubClient


@pytest.fixture
def mock_client(mocker):
    return mocker.MagicMock()


@pytest.fixture
def mock_repo(mocker):
    return mocker.MagicMock()


@pytest.fixture
def mock_release(mocker):
    return mocker.MagicMock()


@pytest.fixture
def github_client_with_mocks(mock_client, mock_repo):
    client = GithubClient()
    mock_client.get_repo.return_value = mock_repo
    client._client = mock_client
    return client


class TestGithubClient:
    def test_clone_repo(self):
        # NOTE: this test actually clones the repo.
        client = GithubClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            client.clone_repo("dapphub/ds-test", temp_dir, branch="master")

    def test_get_release(self, github_client_with_mocks, mock_repo):
        github_client_with_mocks.get_release("test/path", "0.1.0")

        # Test that we used the given tag.
        mock_repo.get_release.assert_called_once_with("0.1.0")

    def test_get_release_when_tag_fails_tries_with_v(
        self, mock_release, github_client_with_mocks, mock_repo
    ):
        # This test makes sure that if we try to get a release and the `v` is not needed,
        # it will try again without the `v`.
        def side_effect(version):
            if version.startswith("v"):
                raise UnknownObjectException("", {}, {})

            return mock_release

        mock_repo.get_release.side_effect = side_effect
        actual = github_client_with_mocks.get_release("test/path", "v0.1.0")
        assert actual == mock_release

    def test_get_release_when_tag_fails_tries_without_v(
        self, mock_release, github_client_with_mocks, mock_repo
    ):
        # This test makes sure that if we try to get a release and the `v` is needed,
        # it will try again with the `v`.
        def side_effect(version):
            if not version.startswith("v"):
                raise UnknownObjectException("", {}, {})

            return mock_release

        mock_repo.get_release.side_effect = side_effect
        actual = github_client_with_mocks.get_release("test/path", "0.1.0")
        assert actual == mock_release
