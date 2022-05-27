import tempfile

from ape.utils.github import GithubClient


class TestGithubClient:
    def test_clone_repo(self):
        # NOTE: this test actually clones the repo.
        client = GithubClient()
        with tempfile.TemporaryDirectory() as temp_dir:
            client.clone_repo("dapphub/ds-test", temp_dir, branch="master")
