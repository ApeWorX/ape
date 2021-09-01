"""
Used with the `docs` Github action to make versioned docs directories in the
gh-pages branch.
"""


import argparse
import os
import re
import shutil
import subprocess
from distutils.version import LooseVersion
from pathlib import Path

REDIRECT_HTML = """
<!DOCTYPE html>
<meta charset="utf-8">
<title>Redirecting...</title>
<meta http-equiv="refresh" content="0; URL=./stable/">
"""

DOCS_BUILD_PATH = Path("docs/_build")


def log(*args, **kwargs):
    print(*args, **kwargs)  # noqa: T001


def run(args):
    log("Running:", args)
    subprocess.check_call(args)


def main():
    # clean out the contents of the build directory, but leave the directory in
    # place so that serving up files continues to work when you're developing
    # docs locally
    DOCS_BUILD_PATH.mkdir(exist_ok=True)
    for path in DOCS_BUILD_PATH.iterdir():
        shutil.rmtree(path) if path.is_dir() else path.unlink()

    if "pull_request" in os.environ.get("GITHUB_EVENT_NAME", ""):
        # build only the current working dir's docs for a PR because PR builds
        # don't have all the refs needed for multiversion
        run(["sphinx-build", "docs", "docs/_build"])
        return  # none of the steps below need to run if we're building for a PR
    else:
        # build docs for each version
        run(["sphinx-multiversion", "docs", "docs/_build"])

    # move the current branch to "latest"
    branch = subprocess.check_output(["git", "branch", "--show-current"]).decode("ascii").strip()
    branch = branch or "main"
    if (DOCS_BUILD_PATH / branch).is_dir():
        Path(DOCS_BUILD_PATH / branch).rename(DOCS_BUILD_PATH / "latest")

    # clean up static files so we don't need to host the same 10+ MB of web
    # fonts for each version of the docs
    for d in Path("docs/_build").glob("**/fonts"):
        if "latest" in str(d):
            continue  # leave only the copy of the static files from the latest version
        shutil.rmtree(d)

    # copy the highest released version to "stable"
    all_releases = [
        LooseVersion(d.name) for d in DOCS_BUILD_PATH.iterdir() if re.match(r"v\d+\.", d.name)
    ]
    no_pre_releases = [v for v in all_releases if "-" not in str(v)]
    stable = None
    if no_pre_releases:
        stable = max(no_pre_releases)
    elif all_releases:
        stable = max(all_releases)
    else:
        log("WARNING: Couldn't find any released versions. Going to use 'latest' for 'stable'.")
        stable = "latest"
    log(f"Copying latest stable release {stable} to 'stable'.")
    shutil.copytree(DOCS_BUILD_PATH / str(stable), DOCS_BUILD_PATH / "stable")

    # set up the redirect at /index.html
    with open(DOCS_BUILD_PATH / "index.html", "w") as f:
        f.write(REDIRECT_HTML)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--rsync",
        help="Where to put the fully built docs subdir for serving in development. "
        "/tmp/projectname is recommended.",
    )
    args = parser.parse_args()

    main()

    if args.rsync:
        run(["rsync", "-pthrvz", "--delete", "./docs/_build/", args.rsync])
        log("\n")
        log(
            (
                "NOTE: To serve these files in development, run `python3 -m http.server` inside "
                "`{}`, then go to http://127.0.0.1:8000/projectname in the browser."
            ).format(Path(args.rsync).parent)
        )
        log(
            "NOTE: If you're making changes to docs locally, go to the 'latest' branch to see "
            "your changes. Also, due to the way sphinx-multiversion integrates with git, you need "
            "to commit your changes each time before building."
        )
        log()
