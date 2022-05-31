import os
import re
import shutil
import tempfile
import zipfile
from io import BytesIO
from pathlib import Path
from typing import Dict, Optional, Set

import pygit2  # type: ignore
from github import Github, UnknownObjectException
from github.GitRelease import GitRelease
from github.Organization import Organization
from github.Repository import Repository as GithubRepository
from pygit2 import Repository as GitRepository
from tqdm.auto import tqdm  # type: ignore

from ape.exceptions import CompilerError, ProjectError
from ape.logging import logger
from ape.utils.misc import USER_AGENT, cached_property, stream_response


class GithubClient:
    """
    An HTTP client for the Github API.
    """

    TOKEN_KEY = "GITHUB_ACCESS_TOKEN"
    _repo_cache: Dict[str, GithubRepository] = {}

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
        The available ``ape`` plugins, found from looking at the ``ApeWorx`` Github organization.

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
        repo = self._client.get_repo(repo_path)

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
        self, repo_path: str, target_path: Path, branch: Optional[str] = None
    ) -> GitRepository:
        """
        Clone a repository from Github.

        Args:
            repo_path (str): The path on Github to the repository,
              e.g. ``OpenZeppelin/openzeppelin-contracts``.
            target_path (Path): The local path to store the repo.
            branch (Optional[str]): The branch to clone. Defaults to the default branch.

        Returns:
            pygit2.repository.Repository
        """

        repo = self.get_repo(repo_path)
        branch = branch or repo.default_branch
        logger.info(f"Cloning branch '{branch}' from '{repo.name}'.")

        class GitRemoteCallbacks(pygit2.RemoteCallbacks):
            percentage_pattern = re.compile(
                r"[1-9]{1,2}% \([1-9]*/[1-9]*\)"
            )  # e.g. '75% (324/432)'
            total_objects: int = 0
            current_objects_cloned: int = 0
            _progress_bar = None

            def sideband_progress(self, string: str):
                # Parse a line like 'Compressing objects:   0% (1/432)'
                string = string.lower()
                expected_prefix = "compressing objects:"
                if expected_prefix not in string:
                    return

                progress_str = string.split(expected_prefix)[-1].strip()

                if not self.percentage_pattern.match(progress_str):
                    return None

                progress_parts = progress_str.split(" ")
                fraction_str = progress_parts[1].lstrip("(").rstrip(")")
                fraction = fraction_str.split("/")
                if not fraction:
                    return

                total_objects = fraction[1]
                if not str(total_objects).isnumeric():
                    return

                GitRemoteCallbacks.total_objects = int(total_objects)
                previous_value = GitRemoteCallbacks.current_objects_cloned
                new_value = int(fraction[0])
                GitRemoteCallbacks.current_objects_cloned = new_value

                if GitRemoteCallbacks.total_objects and not GitRemoteCallbacks._progress_bar:
                    GitRemoteCallbacks._progress_bar = tqdm(range(GitRemoteCallbacks.total_objects))

                difference = new_value - previous_value
                if difference > 0:
                    GitRemoteCallbacks._progress_bar.update(difference)  # type: ignore
                    GitRemoteCallbacks._progress_bar.refresh()  # type: ignore

        url = repo.git_url.replace("git://", "https://")
        clone = pygit2.clone_repository(
            url, str(target_path), checkout_branch=branch, callbacks=GitRemoteCallbacks()
        )
        return clone

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
        if not target_path or not target_path.exists() or not target_path.is_dir():
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
