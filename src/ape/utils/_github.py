import os
import shutil
import struct
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any, ClassVar, NamedTuple

from requests import HTTPError, Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ape.exceptions import CompilerError, ProjectError, UnknownVersionError
from ape.logging import logger
from ape.utils.misc import cached_property
from ape.utils.rpc import USER_AGENT, stream_response

_GITLINK_MODE = 0o160000
"""The git index entry mode of a submodule: a gitlink to a commit in another repository."""

_INDEX_EXTENDED_FLAG = 0x4000
"""The git index entry flag that adds 2 extended flag bytes before the entry's path."""

_INDEX_STAGE_MASK = 0x3000
"""The git index entry flag bits holding the merge stage, 0 outside a merge conflict."""


class GitProcessWrapper:
    @cached_property
    def git(self) -> str:
        if path := shutil.which("git"):
            return path

        raise ProjectError("`git` not installed.")

    def clone(self, url: str, target_path: Path | None = None, branch: str | None = None):
        command = [self.git, "-c", "advice.detachedHead=false", "clone", url]

        if target_path:
            command.append(str(target_path))

        if branch is not None:
            command.extend(("--branch", branch))

        logger.debug(f"Running git command: '{' '.join(command)}'")
        result = subprocess.call(command)
        if result != 0:
            fail_msg = f"`git clone` command failed for '{url}'."

            if branch and not branch.startswith("v"):
                # Often times, `v` is required for tags.
                try:
                    self.clone(url, target_path, branch=f"v{branch}")
                except Exception:  # noqa: BLE001
                    raise ProjectError(fail_msg)

                # Succeeded when prefixing `v`.
                return

            # Failed and we don't really know why.
            # Shouldn't really happen.
            # User will have to run command separately to debug.
            raise ProjectError(fail_msg)

    def get_submodule_commit(self, repo_path: Path, submodule_path: str) -> str | None:
        command = [self.git, "-C", str(repo_path), "ls-tree", "HEAD", submodule_path]
        result = subprocess.run(command, check=False, capture_output=True, text=True)
        if result.returncode != 0:
            return None

        # Output format: `<mode> <type> <object>\t<path>`.
        parts = result.stdout.split()
        return parts[2] if len(parts) >= 3 and parts[1] == "commit" else None


def read_gitlink_from_index(repo_path: Path, submodule_path: str) -> str | None:
    """
    The commit a git submodule is pinned to, read from the parent repository's index file
    without running ``git``.

    A submodule is stored in its parent repository as a "gitlink": an index entry with mode
    ``160000`` whose object ID is the pinned commit of the submodule, not a file blob. This is
    the commit ``git submodule update`` checks out. See the
    `index format <https://git-scm.com/docs/index-format>`__, which defines mode ``160000`` as
    a gitlink (versions 2 and 3 are read here), and
    `submodules <https://git-scm.com/book/en/v2/Git-Tools-Submodules>`__. When ``.git`` is a
    ``gitdir:`` pointer file, as inside a submodule or worktree, the index is read from the
    directory it points to (`repository layout <https://git-scm.com/docs/gitrepository-layout>`__).

    Args:
        repo_path (Path): A directory inside the parent repository.
        submodule_path (str): The submodule's path, relative to ``repo_path``.

    Returns:
        str | None: The pinned commit SHA, or ``None`` when there is no git repository, the
        index is a version this does not read, the path is not a submodule, or its pin is
        in a merge conflict.
    """
    root = next(
        (path for path in (repo_path, *repo_path.parents) if (path / ".git").exists()), None
    )
    if root is None:
        return None

    git_dir = root / ".git"
    if git_dir.is_file():
        pointer = git_dir.read_text(encoding="utf8").strip()
        if not pointer.startswith("gitdir:"):
            return None

        git_dir = root / pointer.removeprefix("gitdir:").strip()

    index_file = git_dir / "index"
    if not index_file.is_file():
        return None

    try:
        entry_path = (repo_path / submodule_path).resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return None

    data = index_file.read_bytes()
    if data[:4] != b"DIRC":
        return None

    (version,) = struct.unpack(">I", data[4:8])
    if version not in (2, 3):
        return None

    for entry in _read_index_entries(data):
        if entry.path == entry_path and entry.stage == 0:
            return entry.sha if entry.mode == _GITLINK_MODE else None

    return None


class _IndexEntry(NamedTuple):
    """One file or submodule entry of a git index."""

    path: str
    mode: int
    sha: str
    stage: int


def _read_index_entries(data: bytes) -> Iterator[_IndexEntry]:
    """The entries of a version 2 or 3 git index file, in index order."""
    (entry_count,) = struct.unpack(">I", data[8:12])
    offset = 12
    for _ in range(entry_count):
        (mode,) = struct.unpack(">I", data[offset + 24 : offset + 28])
        (flags,) = struct.unpack(">H", data[offset + 60 : offset + 62])
        path_start = offset + 62 + (2 if flags & _INDEX_EXTENDED_FLAG else 0)
        path_end = data.index(b"\0", path_start)
        path = data[path_start:path_end].decode("utf8")
        stage = (flags & _INDEX_STAGE_MASK) >> 12
        yield _IndexEntry(path, mode, data[offset + 40 : offset + 60].hex(), stage)
        # Entries are padded with NULs to a multiple of 8 bytes.
        offset += (path_end - offset + 8) // 8 * 8


# NOTE: This client is only meant to be used internally for ApeWorX projects.
class _GithubClient:
    # Generic git/github client attributes.
    TOKEN_KEY = "GITHUB_ACCESS_TOKEN"
    API_URL_PREFIX = "https://api.github.com"
    git: GitProcessWrapper = GitProcessWrapper()

    # ApeWorX-specific attributes.
    ORGANIZATION_NAME = "ApeWorX"
    FRAMEWORK_NAME = "ape"
    _repo_cache: ClassVar[dict[str, dict]] = {}

    def __init__(self, session: Session | None = None):
        if session:
            # NOTE: Mostly allowed for testing purposes.
            self.__session = session

        else:
            headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
            if auth := os.environ.get(self.TOKEN_KEY, None):
                headers["Authorization"] = f"token {auth}"

            session = Session()
            session.headers = {**session.headers, **headers}
            # Belt-and-suspenders: requests also reads HTTP(S)_PROXY from env,
            # which Ape injects from ``proxy`` config during bootstrap.
            from ape.utils.http import get_requests_proxies

            if proxies := get_requests_proxies():
                session.proxies.update(proxies)
            adapter = HTTPAdapter(
                max_retries=Retry(total=10, backoff_factor=1.0, status_forcelist=[403]),
            )
            session.mount("https://", adapter)
            self.__session = session

    @cached_property
    def org(self) -> dict:
        """
        Our organization on ``Github``.
        """
        return self.get_organization(self.ORGANIZATION_NAME)

    @cached_property
    def available_plugins(self) -> set[str]:
        return {
            repo["name"].replace("-", "_")
            for repo in self.get_org_repos()
            if not repo.get("private", False) and repo["name"].startswith(f"{self.FRAMEWORK_NAME}-")
        }

    def get_org_repos(self) -> Iterator[dict]:
        params = {"per_page": 100, "page": 1}
        while True:
            response = self._get(f"orgs/{self.ORGANIZATION_NAME}/repos", params=params)
            repository_count = len(response)

            if repository_count == 0:
                break

            yield from response
            params["page"] += 1

    def get_release(self, org_name: str, repo_name: str, version: str) -> dict:
        if version == "latest":
            return self.get_latest_release(org_name, repo_name)

        def _try_get_release(vers):
            try:
                return self._get_release(org_name, repo_name, vers)
            except Exception:  # noqa: BLE001
                return None

        if release := _try_get_release(version):
            return release
        else:
            original_version = str(version)
            # Try an alternative tag style
            if version.startswith("v"):
                version = version.lstrip("v")
            else:
                version = f"v{version}"

            if release := _try_get_release(version):
                return release

            raise UnknownVersionError(original_version, repo_name)

    def _get_release(self, org_name: str, repo_name: str, version: str) -> dict:
        return self._get(f"repos/{org_name}/{repo_name}/releases/tags/{version}")

    def get_repo(self, org_name: str, repo_name: str) -> dict:
        repo_path = f"{org_name}/{repo_name}"
        if repo_path not in self._repo_cache:
            try:
                self._repo_cache[repo_path] = self._get_repo(org_name, repo_name)
                return self._repo_cache[repo_path]
            except Exception as err:
                raise ProjectError(f"Unknown repository '{repo_path}'") from err

        return self._repo_cache[repo_path]

    def _get_repo(self, org_name: str, repo_name: str) -> dict:
        try:
            return self._get(f"repos/{org_name}/{repo_name}")
        except HTTPError as err:
            if err.response.status_code == 404:
                raise ProjectError(f"Unknown repository '{org_name}/{repo_name}'")

            raise  # The original HTTPError

    def get_latest_release(self, org_name: str, repo_name: str) -> dict:
        return self._get(f"repos/{org_name}/{repo_name}/releases/latest")

    def get_organization(self, org_name: str) -> dict:
        return self._get(f"orgs/{org_name}")

    def clone_repo(
        self,
        org_name: str,
        repo_name: str,
        target_path: str | Path,
        branch: str | None = None,
        scheme: str = "https",
    ):
        repo = self.get_repo(org_name, repo_name)
        branch = branch or repo["default_branch"]
        logger.info(f"Cloning branch '{branch}' from '{repo['name']}'.")
        url = repo["git_url"]

        if "ssh" in scheme or "git" in scheme:
            url = url.replace("git://github.com/", "git@github.com:")
        elif "http" in scheme:
            url = url.replace("git://", "https://")
        else:
            raise ValueError(f"Scheme '{scheme}' not supported.")

        target_path = Path(target_path)
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_path.exists():
            # Target repo cannot exist.
            target_path = target_path / repo_name

        self.git.clone(url, branch=branch, target_path=target_path)

    def download_package(
        self, org_name: str, repo_name: str, version: str, target_path: Path | str
    ):
        release = self.get_release(org_name, repo_name, version)
        self._download_zipball(release["zipball_url"], org_name, repo_name, version, target_path)

    def download_ref(self, org_name: str, repo_name: str, ref: str, target_path: Path | str):
        url = f"{self.API_URL_PREFIX}/repos/{org_name}/{repo_name}/zipball/{ref}"
        self._download_zipball(url, org_name, repo_name, ref, target_path)

    def _download_zipball(
        self, url: str, org_name: str, repo_name: str, version: str, target_path: Path | str
    ):
        target_path = Path(target_path)  # Handles str
        if not target_path or not target_path.is_dir():
            raise ValueError(f"'target_path' must be a valid directory (got '{target_path}').")

        description = f"Downloading {org_name}/{repo_name}@{version}"
        zipball_content = stream_response(url, progress_bar_description=description)

        # Use temporary path to isolate a package when unzipping
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            temp_path = Path(tmp)
            with zipfile.ZipFile(BytesIO(zipball_content)) as zf:
                zf.extractall(temp_path)

            # Copy the directory contents into the target path.
            downloaded_packages = [f for f in temp_path.iterdir() if f.is_dir()]
            if len(downloaded_packages) < 1:
                raise CompilerError(f"Unable to download package at '{org_name}/{repo_name}'.")

            package_path = temp_path / downloaded_packages[0]
            for source_file in package_path.iterdir():
                shutil.move(str(source_file), str(target_path))

    def _get(self, url: str, params: dict | None = None) -> Any:
        return self._request("GET", url, params=params)

    def _request(self, method: str, url: str, **kwargs) -> Any:
        url = f"{self.API_URL_PREFIX}/{url}"
        response = self.__session.request(method, url, **kwargs)

        try:
            response.raise_for_status()
        except HTTPError as err:
            if err.response.status_code == 401 and self.__session.headers.get("Authorization"):
                token = self.__session.headers["Authorization"]
                del self.__session.headers["Authorization"]
                response = self.__session.request(method, url, **kwargs)
                try:
                    response.raise_for_status()  # Raise exception if the retry also fails
                except HTTPError:
                    # Even without the Authorization token, the request still failed.
                    # Raise the original error in this case. Also, put back token just in case.
                    self.__session.headers["Authorization"] = token
                    raise err
                else:
                    # The request failed with Authorization but succeeded without.
                    # Let the user know their token is likely expired.
                    logger.warning(
                        "Requests are not authorized! GITHUB_ACCESS_TOKEN is likely expired; "
                        "received 401 when attempted to use it. If you need GitHub authorization, "
                        "try resetting your token."
                    )
                    return response.json()

            raise  # Raise the error.

        return response.json()


github_client = _GithubClient()
