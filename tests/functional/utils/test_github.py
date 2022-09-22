import tempfile

import pytest
from github import UnknownObjectException

from ape.utils.github import GithubClient, GitRemoteCallbacks

REPO_PATH = "test/path"


@pytest.fixture(autouse=True)
def clear_repo_cache(github_client_with_mocks):
    def clear():
        if REPO_PATH in github_client_with_mocks._repo_cache:
            del github_client_with_mocks._repo_cache[REPO_PATH]

    clear()
    yield
    clear()


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
    def test_clone_repo(self, mocker):
        # NOTE: this test actually clones the repo.
        client = GithubClient()
        git_patch = mocker.patch("ape.utils.github.pygit2.clone_repository")
        with tempfile.TemporaryDirectory() as temp_dir:
            client.clone_repo("dapphub/ds-test", temp_dir, branch="master")

        call_args = git_patch.call_args[0]
        call_kwargs = git_patch.call_args[1]
        assert call_args[0] == "https://github.com/dapphub/ds-test.git"
        assert call_args[1]
        assert call_kwargs["checkout_branch"] == "master"

        # Test callbacks
        callbacks = call_kwargs["callbacks"]
        progress_str = "remote: Compressing objects: 95% (62/65)."
        callbacks.sideband_progress(progress_str)
        assert GitRemoteCallbacks.total_objects == 65
        assert GitRemoteCallbacks.current_objects_cloned == 62

    def test_get_release(self, github_client_with_mocks, mock_repo):
        github_client_with_mocks.get_release(REPO_PATH, "0.1.0")

        # Test that we used the given tag.
        mock_repo.get_release.assert_called_once_with("0.1.0")

        # Ensure that it uses the repo cache the second time
        github_client_with_mocks.get_release(REPO_PATH, "0.1.0")
        assert github_client_with_mocks._client.get_repo.call_count == 1

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
        actual = github_client_with_mocks.get_release(REPO_PATH, "v0.1.0")
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
        actual = github_client_with_mocks.get_release(REPO_PATH, "0.1.0")
        assert actual == mock_release
