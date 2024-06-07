from pathlib import Path

import pytest
from requests.exceptions import ConnectTimeout

from ape.utils._github import _GithubClient
from ape.utils.os import create_tempdir

ORG_NAME = "test"
REPO_NAME = "path"
REPO_PATH = f"{ORG_NAME}/{REPO_NAME}"


@pytest.fixture(autouse=True)
def clear_repo_cache(github_client):
    def clear():
        if REPO_PATH in github_client._repo_cache:
            del github_client._repo_cache[REPO_PATH]

    clear()
    yield
    clear()


@pytest.fixture
def mock_session(mocker):
    return mocker.MagicMock()


@pytest.fixture
def mock_release(mocker):
    release = mocker.MagicMock()
    release.json.return_value = {"name": REPO_NAME}
    return release


@pytest.fixture
def github_client(mock_session):
    return _GithubClient(session=mock_session)


class TestGithubClient:
    def test_clone_repo(self, mocker):
        # NOTE: this test actually clones the repo.
        client = _GithubClient()
        git_patch = mocker.patch("ape.utils._github.subprocess.call")
        git_patch.return_value = 0
        with create_tempdir() as temp_dir:
            try:
                client.clone_repo("dapphub", "ds-test", Path(temp_dir), branch="master")
            except ConnectTimeout:
                pytest.xfail("Internet required to run this test.")

        cmd = git_patch.call_args[0][0]
        assert cmd[0].endswith("git")
        assert cmd[1] == "-c"
        assert cmd[2] == "advice.detachedHead=false"
        assert cmd[3] == "clone"
        assert cmd[4] == "https://github.com/dapphub/ds-test.git"
        # cmd[5] is the temporary output path
        assert cmd[6] == "--branch"
        assert cmd[7] == "master"

    def test_get_release(self, github_client, mock_session):
        version = "0.1.0"
        github_client.get_release(ORG_NAME, REPO_NAME, "0.1.0")
        base_uri = f"https://api.github.com/repos/{ORG_NAME}/{REPO_NAME}/releases/tags"
        expected_uri = f"{base_uri}/{version}"
        assert mock_session.request.call_args[0] == ("GET", expected_uri)

    @pytest.mark.parametrize("version", ("0.1.0", "v0.1.0"))
    def test_get_release_retry(self, mock_release, github_client, mock_session, version):
        """
        Ensure after failing to get a release, we re-attempt with
        out a v-prefix.
        """
        opposite = version.lstrip("v") if version.startswith("v") else f"v{version}"

        def side_effect(method, uri, *arg, **kwargs):
            _version = uri.split("/")[-1]
            if _version == version:
                # Force it to try the opposite.
                raise ValueError()

            return mock_release

        mock_session.request.side_effect = side_effect
        actual = github_client.get_release(ORG_NAME, REPO_NAME, version)
        assert actual["name"] == REPO_NAME
        calls = mock_session.request.call_args_list[-2:]
        expected_uri = "https://api.github.com/repos/test/path/releases/tags"
        assert calls[0][0] == ("GET", f"{expected_uri}/{version}")
        assert calls[1][0] == ("GET", f"{expected_uri}/{opposite}")

    def test_get_org_repos(self, github_client, mock_session):
        _ = list(github_client.get_org_repos())
        call = mock_session.method_calls[-1]
        params = call.kwargs["params"]
        # Show we are fetching more than the default 30 per page.
        assert params == {"per_page": 100, "page": 1}
