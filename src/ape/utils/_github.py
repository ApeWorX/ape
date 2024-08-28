import os
import shutil
import subprocess
import tempfile
import zipfile
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any, Optional, Union

from requests import Session
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from ape.exceptions import CompilerError, ProjectError, UnknownVersionError
from ape.logging import logger
from ape.utils.misc import cached_property
from ape.utils.rpc import USER_AGENT, stream_response


class GitProcessWrapper:
    @cached_property
    def git(self) -> str:
        if path := shutil.which("git"):
            return path

        raise ProjectError("`git` not installed.")

    def clone(self, url: str, target_path: Optional[Path] = None, branch: Optional[str] = None):
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
                except Exception:
                    raise ProjectError(fail_msg)

                # Succeeded when prefixing `v`.
                return

            # Failed and we don't really know why.
            # Shouldn't really happen.
            # User will have to run command separately to debug.
            raise ProjectError(fail_msg)


# NOTE: This client is only meant to be used internally for ApeWorX projects.
class _GithubClient:
    # Generic git/github client attributes.
    TOKEN_KEY = "GITHUB_ACCESS_TOKEN"
    API_URL_PREFIX = "https://api.github.com"
    git: GitProcessWrapper = GitProcessWrapper()

    # ApeWorX-specific attributes.
    ORGANIZATION_NAME = "ApeWorX"
    FRAMEWORK_NAME = "ape"
    _repo_cache: dict[str, dict] = {}

    def __init__(self, session: Optional[Session] = None):
        if session:
            # NOTE: Mostly allowed for testing purposes.
            self.__session = session

        else:
            headers = {"Content-Type": "application/json", "User-Agent": USER_AGENT}
            if auth := os.environ[self.TOKEN_KEY] if self.TOKEN_KEY in os.environ else None:
                headers["Authorization"] = f"token {auth}"

            session = Session()
            session.headers = {**session.headers, **headers}
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
            except Exception:
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

        else:
            return self._repo_cache[repo_path]

    def _get_repo(self, org_name: str, repo_name: str) -> dict:
        return self._get(f"repos/{org_name}/{repo_name}")

    def get_latest_release(self, org_name: str, repo_name: str) -> dict:
        return self._get(f"repos/{org_name}/{repo_name}/releases/latest")

    def get_organization(self, org_name: str) -> dict:
        return self._get(f"orgs/{org_name}")

    def clone_repo(
        self,
        org_name: str,
        repo_name: str,
        target_path: Union[str, Path],
        branch: Optional[str] = None,
        scheme: str = "http",
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
        self, org_name: str, repo_name: str, version: str, target_path: Union[Path, str]
    ):
        target_path = Path(target_path)  # Handles str
        if not target_path or not target_path.is_dir():
            raise ValueError(f"'target_path' must be a valid directory (got '{target_path}').")

        release = self.get_release(org_name, repo_name, version)
        description = f"Downloading {org_name}/{repo_name}@{version}"
        release_content = stream_response(
            release["zipball_url"], progress_bar_description=description
        )

        # Use temporary path to isolate a package when unzipping
        with tempfile.TemporaryDirectory() as tmp:
            temp_path = Path(tmp)
            with zipfile.ZipFile(BytesIO(release_content)) as zf:
                zf.extractall(temp_path)

            # Copy the directory contents into the target path.
            downloaded_packages = [f for f in temp_path.iterdir() if f.is_dir()]
            if len(downloaded_packages) < 1:
                raise CompilerError(f"Unable to download package at '{org_name}/{repo_name}'.")

            package_path = temp_path / downloaded_packages[0]
            for source_file in package_path.iterdir():
                shutil.move(str(source_file), str(target_path))

    def _get(self, url: str, params: Optional[dict] = None) -> Any:
        return self._request("GET", url, params=params)

    def _request(self, method: str, url: str, **kwargs) -> Any:
        url = f"{self.API_URL_PREFIX}/{url}"
        response = self.__session.request(method, url, **kwargs)
        response.raise_for_status()
        return response.json()


github_client = _GithubClient()
