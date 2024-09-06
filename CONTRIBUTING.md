# Development

To get started with working on the codebase, use the following steps to prepare your local environment:

```bash
# clone the GitHub repo and navigate into the folder
git clone https://github.com/ApeWorX/ape.git
cd ape

# create and load a virtual environment
python3 -m venv venv
source venv/bin/activate

# install the developer dependencies (-e is interactive mode)
pip install -e .'[dev]'
```

```{note}
You might run into issues where you have a local install and are trying to work with a plugin pinned to a specific version.
```

[The easiest solution](https://github.com/ApeWorX/ape/issues/90) to this is to fetch the tags via `git fetch upstream --tags` and reinstall via `pip install .`.
You will then have the correct version.

## Pre-Commit Hooks

We use [`pre-commit`](https://pre-commit.com/) hooks to simplify linting and ensure consistent formatting among contributors.
Use of `pre-commit` is not a requirement, but is highly recommended.

Install `pre-commit` locally from the root folder:

```bash
pip install pre-commit
pre-commit install
```

Committing will now automatically run the local hooks and ensure that your commit passes all lint checks.

## GitHub Access Token

If you are a member of ApeWorX and would like to install private plugins,
[create a GitHub access token](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/creating-a-personal-access-token).

Once you have your token, export it to your terminal session:

```bash
export GITHUB_ACCESS_TOKEN=<your-token>
```

## Running the docs locally

First, make sure you have the docs-related tooling installed:

```bash
pip install -e .'[doc]'
```

Then, run the following from the root project directory:

```bash
sphinx-ape build .
```

For the best viewing experience, use a local server:

```bash
sphinx-ape serve .
```

Then, open your browser to `127.0.0.1:1337` and click the `ape` directory link.

You can also use the `--open` flag to automatically open the docs:

```bash
sphinx-ape serve . --open
```

## Pull Requests

Pull requests are welcomed! Please adhere to the following:

- Ensure your pull request passes our linting checks
- Include test cases for any new functionality
- Include any relevant documentation updates

It's a good idea to make pull requests early on.
A pull request represents the start of a discussion, and doesn't necessarily need to be the final, finished submission.

If you are opening a work-in-progress pull request to verify that it passes CI tests, please consider
[marking it as a draft](https://help.github.com/en/github/collaborating-with-issues-and-pull-requests/about-pull-requests#draft-pull-requests).

Join the ApeWorX [Discord](https://discord.gg/apeworx) if you have any questions.
