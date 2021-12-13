import os
import shutil
import subprocess
from pathlib import Path

REDIRECT_HTML = """
<!DOCTYPE html>
<meta charset="utf-8">
<title>Redirecting...</title>
<meta http-equiv="refresh" content="0; URL=./stable/">
"""
DOCS_BUILD_PATH = Path("docs/_build")
LATEST_PATH = DOCS_BUILD_PATH / "latest"
STABLE_PATH = DOCS_BUILD_PATH / "stable"
LOCAL_PATH = DOCS_BUILD_PATH / "development"


class DocsBuildError(Exception):
    pass


def run(*args):
    subprocess.check_call([*args])


def git(*args):
    return subprocess.check_output(["git", *args]).decode("ascii").strip()


def new_dir(path: Path) -> Path:
    if path.exists():
        shutil.rmtree(path)

    path.mkdir(parents=True)
    return path


def build_docs(path: Path) -> Path:
    path = new_dir(path)
    run("sphinx-build", "docs", path)
    return path


def build_docs_from_push_to_main():
    build_docs(LATEST_PATH)

    if not STABLE_PATH.exists():
        # 'stable/' required for serving.
        # If we have never released, just use 'latest/' as 'stable'/
        shutil.copytree(LATEST_PATH, STABLE_PATH)


def build_docs_from_release():
    """
    When building the docs from a release, we create a new release
    directory and copy the 'latest/' docs into it. We also copy the
    'latest/' docs into the 'stable/' directory.
    """

    tag = git("describe", "--tag")
    if not tag:
        raise DocsBuildError("Unable to find release tag.")

    new_version_dir = DOCS_BUILD_PATH / tag

    if not LATEST_PATH.exists():
        # This should already exist from the last push to 'main'.
        # But just in case, we can build it now.
        build_docs(LATEST_PATH)

    # Copy the latest build from 'main' to the new version dir.
    shutil.copytree(LATEST_PATH, new_version_dir)

    # Copy the latest build from 'main' to the 'stable' dir.
    if STABLE_PATH.exists():
        shutil.rmtree(STABLE_PATH)
    shutil.copytree(LATEST_PATH, STABLE_PATH)

    # Clean-up unnecessary extra 'fonts/' directories to save space.
    for font_dirs in DOCS_BUILD_PATH.glob("**/fonts"):
        if font_dirs.exists():
            shutil.rmtree(font_dirs)


def main():
    event_name = os.environ.get("GITHUB_EVENT_NAME")

    # There are three GH events we build for:
    #
    # 1. Push to main: we build into 'latest/'.
    #    The GH action will commit these changes to the 'gh-pages' branch.
    #
    # 2. Release: we copy 'latest/' into the release dir, as well as to 'stable/'.
    #    The GH action will commit these changes to the 'gh-pages' branch.
    #
    # 3. Pull requests or local development: We ensure a successful build.
    #

    if event_name == "push":  # Is 'push' to branch 'main'.
        build_docs_from_push_to_main()
    elif event_name == "release":
        build_docs_from_release()
    elif event_name in ["pull_request", None]:
        build_docs(LOCAL_PATH)

    # Set up the redirect at /index.html
    with open(DOCS_BUILD_PATH / "index.html", "w") as f:
        f.write(REDIRECT_HTML)


if __name__ == "__main__":
    main()
