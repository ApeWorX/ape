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


def build_docs_from_release():
    """
    When building the docs from a release, we create a new release
    directory and copy the 'latest/' docs into it. We also copy the
    'latest/' docs into the 'stable/' directory.
    """

    tag = git("describe", "--tag")
    if not tag:
        raise DocsBuildError("Unable to find release tag.")

    new_version_dir = new_dir(DOCS_BUILD_PATH / tag)

    latest_docs_build = DOCS_BUILD_PATH / "latest"
    if not latest_docs_build.exists():
        # This should already exist from the last push to 'main'.
        # But just in case, we can build it now.
        build_docs(latest_docs_build)

    # Copy the latest build from 'main' to the new version dir.
    shutil.copytree(latest_docs_build, new_version_dir)

    # Copy the latest build from 'main' to the 'stable' dir.
    shutil.copytree(latest_docs_build, DOCS_BUILD_PATH / "stable")

    # Clean-up unnecessary extra 'fonts/' directories to save space.
    for font_dirs in DOCS_BUILD_PATH.glob("**/fonts"):
        if font_dirs.exists():
            shutil.rmtree(font_dirs)


def main():
    event_name = os.environ.get("GITHUB_EVENT_NAME")

    if event_name == "push":
        build_docs(DOCS_BUILD_PATH / "latest")
    elif event_name == "release":
        build_docs_from_release()
    elif event_name in ["pull_request", None]:
        build_docs(DOCS_BUILD_PATH / "development")

    # Set up the redirect at /index.html
    with open(DOCS_BUILD_PATH / "index.html", "w") as f:
        f.write(REDIRECT_HTML)


if __name__ == "__main__":
    main()
