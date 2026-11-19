import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from requests.exceptions import ConnectTimeout, HTTPError

from ape.exceptions import ProjectError
from ape.utils._github import _GithubClient, read_gitlink_from_index
from ape.utils.os import create_tempdir
from tests.functional.conftest import GitIndexEntry

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


@pytest.fixture(scope="session")
def commit_sha():
    return "1" * 40


@pytest.fixture(scope="session")
def commit_zipball(commit_sha):
    content = BytesIO()
    with zipfile.ZipFile(content, "w") as archive:
        archive.writestr(f"{ORG_NAME}-{REPO_NAME}-{commit_sha[:7]}/foundry.toml", "")

    return content.getvalue()


@pytest.fixture
def mock_stream_response(mocker, commit_zipball):
    return mocker.patch("ape.utils._github.stream_response", return_value=commit_zipball)


@pytest.fixture
def github_client(mock_session):
    return _GithubClient(session=mock_session)


class TestGithubClient:
    def test_get_repo_unknown_repo(self, mocker, mock_session):
        client = _GithubClient(session=mock_session)

        # Make it raise 404.
        response = mocker.MagicMock()
        response.status_code = 404
        error = HTTPError(response=response)
        mock_session.request.side_effect = error

        with pytest.raises(ProjectError, match=f"Unknown repository '{ORG_NAME}/{REPO_NAME}'"):
            client.get_repo(ORG_NAME, REPO_NAME)

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

    def test_download_ref_commit(self, github_client, mock_stream_response, tmp_path, commit_sha):
        github_client.download_ref(ORG_NAME, REPO_NAME, commit_sha, tmp_path)

        expected_uri = f"https://api.github.com/repos/{ORG_NAME}/{REPO_NAME}/zipball/{commit_sha}"
        assert mock_stream_response.call_args[0] == (expected_uri,)
        assert (tmp_path / "foundry.toml").is_file()

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

    def test_available_plugins(self, mocker, github_client, mock_session):
        response1 = mocker.MagicMock()
        response1.json.return_value = [{"name": "ape-myplugin"}]
        response2 = mocker.MagicMock()
        response2.json.return_value = []

        def get_org_repos(method, url, **kwargs):
            if kwargs["params"]["page"] == 1:
                return response1
            else:
                # End.
                return response2

        mock_session.request.side_effect = get_org_repos
        actual = github_client.available_plugins
        assert actual == {"ape_myplugin"}

    def test_available_plugins_handles_401(self, mocker, github_client, mock_session, ape_caplog):
        """
        When you get a 401 from using a token, Ape's GitHub client should not
        only warn the user but retry the request w/o authorization, as it likely
        will still work.
        """
        mock_session.headers = {"Authorization": "token mytoken"}

        response1 = mocker.MagicMock()
        response1.json.return_value = [{"name": "ape-myplugin"}]
        response2 = mocker.MagicMock()
        response2.json.return_value = []

        bad_auth_response = mocker.MagicMock()
        bad_auth_response.status_code = 401
        bad_auth_response.raise_for_status.side_effect = HTTPError(response=bad_auth_response)

        def get_org_repos(method, url, **kwargs):
            if mock_session.headers.get("Authorization") == "token mytoken":
                return bad_auth_response
            elif kwargs["params"]["page"] == 1:
                return response1
            else:
                # End.
                return response2

        mock_session.request.side_effect = get_org_repos
        actual = github_client.available_plugins

        # Still works, even with bad auth.
        assert actual == {"ape_myplugin"}

        # Show we got our log message.
        expected = (
            "Requests are not authorized! GITHUB_ACCESS_TOKEN is likely "
            "expired; received 401 when attempted to use it. If you need "
            "GitHub authorization, try resetting your token."
        )
        assert ape_caplog.head == expected


class TestReadGitlinkFromIndex:
    @pytest.fixture(scope="session")
    def gitlink(self, commit_sha):
        return GitIndexEntry("lib/dependency", 0o160000, commit_sha)

    @pytest.fixture(scope="session")
    def regular_file(self):
        return GitIndexEntry("readme.md", 0o100644, "2" * 40)

    def test_read_gitlink_from_index_gitlink(self, tmp_path, write_git_index, gitlink):
        write_git_index(tmp_path, [gitlink])
        assert read_gitlink_from_index(tmp_path, "lib/dependency") == gitlink.sha

    def test_read_gitlink_from_index_subdirectory(self, tmp_path, write_git_index, gitlink):
        write_git_index(tmp_path, [gitlink])
        assert read_gitlink_from_index(tmp_path / "lib", "dependency") == gitlink.sha

    def test_read_gitlink_from_index_not_a_gitlink(
        self, tmp_path, write_git_index, gitlink, regular_file
    ):
        write_git_index(tmp_path, [regular_file, gitlink])
        assert read_gitlink_from_index(tmp_path, "readme.md") is None
        assert read_gitlink_from_index(tmp_path, "missing") is None

    @pytest.mark.parametrize(
        "earlier_entry",
        [
            pytest.param(GitIndexEntry("a.txt", 0o100644, "2" * 40, extended=True), id="extended"),
            pytest.param(GitIndexEntry("a-\u00e9t\u00e9.txt", 0o100644, "2" * 40), id="non-ascii"),
            pytest.param(GitIndexEntry("a" * 0x1000 + ".txt", 0o100644, "2" * 40), id="long-path"),
        ],
    )
    def test_read_gitlink_from_index_after_unusual_entry(
        self, tmp_path, write_git_index, gitlink, earlier_entry
    ):
        write_git_index(tmp_path, [earlier_entry, gitlink], version=3)
        assert read_gitlink_from_index(tmp_path, "lib/dependency") == gitlink.sha

    def test_read_gitlink_from_index_gitdir_file(self, tmp_path, write_git_index, gitlink):
        project = tmp_path / "project"
        project.mkdir()
        write_git_index(project, [gitlink], gitdir=tmp_path / "modules" / "project")
        assert read_gitlink_from_index(project, "lib/dependency") == gitlink.sha

    def test_read_gitlink_from_index_version_4(self, tmp_path, write_git_index, gitlink):
        write_git_index(tmp_path, [gitlink], version=4)
        assert read_gitlink_from_index(tmp_path, "lib/dependency") is None

    def test_read_gitlink_from_index_unreadable(self, tmp_path, write_git_index, gitlink):
        project = tmp_path / "project"
        project.mkdir()
        index_file = write_git_index(project, [gitlink])
        index_file.write_bytes(b"XXXX" + index_file.read_bytes()[4:])
        assert read_gitlink_from_index(project, "lib/dependency") is None
        no_repo = tmp_path / "no-repo"
        no_repo.mkdir()
        assert read_gitlink_from_index(no_repo, "lib/dependency") is None

    def test_read_gitlink_from_index_merge_conflict(self, tmp_path, write_git_index, gitlink):
        conflict = [gitlink._replace(stage=stage, sha=str(stage) * 40) for stage in (1, 2, 3)]
        write_git_index(tmp_path, conflict)
        assert read_gitlink_from_index(tmp_path, "lib/dependency") is None
