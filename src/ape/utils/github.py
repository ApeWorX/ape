import os
import shutil
import subprocess
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional, Set

from github import Github, UnknownObjectException
from github.GitRelease import GitRelease
from github.Organization import Organization
from github.Repository import Repository as GithubRepository

from ape.exceptions import CompilerError, ProjectError
from ape.logging import logger
from ape.utils.misc import USER_AGENT, cached_property, stream_response


class GitProcessWrapper:
    @cached_property
    def git(self) -> str:
        git_cmd_path = shutil.which("git")
        if not git_cmd_path:
            raise ProjectError("`git` not installed.")

        return git_cmd_path

    def clone(self, url: str, target_path: Optional[Path] = None, branch: Optional[str] = None):
        command = [self.git, "clone", url]

        if target_path:
            command.append(str(target_path))

        if branch is not None:
            command.extend(("--branch", branch))

        logger.debug(f"Running git command: '{' '.join(command)}'")
        result = subprocess.call(command)
        if result != 0:
            raise ProjectError(f"`git clone` command failed for '{url}'.")


class GithubClient:
    """
    An HTTP client for the Github API.
    """

    TOKEN_KEY = "GITHUB_ACCESS_TOKEN"
    _repo_cache: Dict[str, GithubRepository] = {}
    git: GitProcessWrapper = GitProcessWrapper()

    def __init__(self):
        token = os.environ[self.TOKEN_KEY] if self.TOKEN_KEY in os.environ else None
        self._client = Github(login_or_token=token, user_agent=USER_AGENT)

    @cached_property
    def ape_org(self) -> Organization:
        """
        The ``ApeWorX`` organization on ``Github`` (https://github.com/ApeWorX).
        """
        return self._client.get_organization("ApeWorX")

    @cached_property
    def available_plugins(self) -> Set[str]:
        """
        The available ``ape`` plugins, found from looking at the ``ApeWorX`` Github organization.

        Returns:
            Set[str]: The plugin names as ``'ape_plugin_name'`` (module-like).
        """
        return {
            repo.name.replace("-", "_")
            for repo in self.ape_org.get_repos()
            if not repo.private and repo.name.startswith("ape-")
        }

    def get_release(self, repo_path: str, version: str) -> GitRelease:
        """
        Get a release from Github.

        Args:
            repo_path (str): The path on Github to the repository,
              e.g. ``OpenZeppelin/openzeppelin-contracts``.
            version (str): The version of the release to get. Pass in ``"latest"``
              to get the latest release.

        Returns:
            github.GitRelease.GitRelease
        """
        repo = self.get_repo(repo_path)

        if version == "latest":
            return repo.get_latest_release()

        def _try_get_release(vers):
            try:
                return repo.get_release(vers)
            except UnknownObjectException:
                return None

        release = _try_get_release(version)
        if not release:
            original_version = str(version)
            # Try an alternative tag style
            if version.startswith("v"):
                version = version.lstrip("v")
            else:
                version = f"v{version}"

            release = _try_get_release(version)
            if not release:
                raise ProjectError(f"Unknown version '{original_version}' for repo '{repo.name}'.")

        return release

    def get_repo(self, repo_path: str) -> GithubRepository:
        """
        Get a repository from GitHub.

        Args:
            repo_path (str): The path to the repository, such as
              ``OpenZeppelin/openzeppelin-contracts``.

        Returns:
            github.Repository.Repository
        """

        if repo_path not in self._repo_cache:
            try:
                self._repo_cache[repo_path] = self._client.get_repo(repo_path)
                return self._repo_cache[repo_path]
            except UnknownObjectException as err:
                raise ProjectError(f"Unknown repository '{repo_path}'") from err

        else:
            return self._repo_cache[repo_path]

    def clone_repo(
        self,
        repo_path: str,
        target_path: Path,
        branch: Optional[str] = None,
        scheme: str = "http",
    ):
        """
        Clone a repository from Github.

        Args:
            repo_path (str): The path on Github to the repository,
              e.g. ``OpenZeppelin/openzeppelin-contracts``.
            target_path (Path): The local path to store the repo.
            branch (Optional[str]): The branch to clone. Defaults to the default branch.
            scheme (str): The git scheme to use when cloning. Defaults to `ssh`.
        """

        repo = self.get_repo(repo_path)
        branch = branch or repo.default_branch
        logger.info(f"Cloning branch '{branch}' from '{repo.name}'.")
        url = repo.git_url

        if "ssh" in scheme or "git" in scheme:
            url = url.replace("git://github.com/", "git@github.com:")
        elif "http" in scheme:
            url = url.replace("git://", "https://")
        else:
            raise ValueError(f"Scheme '{scheme}' not supported.")

        self.git.clone(url, branch=branch, target_path=target_path)

    def download_package(self, repo_path: str, version: str, target_path: Path):
        """
        Download a package from Github. This is useful for managing project dependencies.

        Args:
            repo_path (str): The path on ``Github`` to the repository,
                                such as ``OpenZeppelin/openzeppelin-contracts``.
            version (str): Number to specify update types
                                to the downloaded package.
            target_path (path): A path in your local filesystem to save the downloaded package.
        """
        if not target_path or not target_path.is_dir():
            raise ValueError(f"'target_path' must be a valid directory (got '{target_path}').")

        release = self.get_release(repo_path, version)
        description = f"Downloading {repo_path}@{version}"
        release_content = stream_response(release.zipball_url, progress_bar_description=description)

        # Use temporary path to isolate a package when unzipping
        with tempfile.TemporaryDirectory() as tmp:
            temp_path = Path(tmp)
            with zipfile.ZipFile(BytesIO(release_content)) as zf:
                zf.extractall(temp_path)

            # Copy the directory contents into the target path.
            downloaded_packages = [f for f in temp_path.iterdir() if f.is_dir()]
            if len(downloaded_packages) < 1:
                raise CompilerError(f"Unable to download package at '{repo_path}'.")

            package_path = temp_path / downloaded_packages[0]
            for source_file in package_path.iterdir():
                shutil.move(str(source_file), str(target_path))


github_client = GithubClient()
