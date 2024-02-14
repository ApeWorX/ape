[![Pypi.org][pypi-badge]][pypi-url]
[![Apache licensed][licence-badge]][licence-url]
[![Build Status][actions-badge]][actions-url]
[![Discord chat][discord-badge]][discord-url]
[![Twitter][twitter-badge]][twitter-url]

# Overview

[Ape Framework](https://apeworx.io/framework/) is an easy-to-use Web3 development tool.
Users can compile, test, and interact with smart contracts all in one command line session.
With our [modular plugin system](#plugin-system), Ape supports multiple contract languages and chains.

Ape is built by [ApeWorX LTD](https://www.apeworx.io/).

Join our [ApeWorX Discord server][discord-url] to stay up to date on new releases, plugins, and tutorials.

If you want to get started now, see the [Quickstart](#quickstart) section.

## Documentation

Read our [technical documentation](https://docs.apeworx.io/ape/stable/) to get a deeper understanding of our open source Framework.

Read our [academic platform](https://academy.apeworx.io/) will help you master Ape Framework with tutorials and challenges.

## Prerequisite

In the latest release, Ape requires:

- Linux or macOS
- Python 3.8 up to 3.11
- **Windows**: Install Windows Subsystem Linux [(WSL)](https://docs.microsoft.com/en-us/windows/wsl/install)

Check your python version in a terminal with `python3 --version`.

## Installation

There are three ways to install ape: `pipx`, `pip`, or `Docker`.

### Considerations for Installing

- If using `pip`, we advise using the most up-to-date version of `pip` to increase the chance of a successful installation.

  - See issue https://github.com/ApeWorX/ape/issues/1558.
  - To upgrade `pip` from the command line, run: `pip install --upgrade pip`.

- We advise installing in a [virtualenv](https://pypi.org/project/virtualenv/) or [venv](https://docs.python.org/3/library/venv.html) to avoid interfering with *OS-level site packages*.

- We advise installing **`ape`** with recommended plugins `pip install eth-ape'[recommended-plugins]'`.

- We advise for **macOS** users to install virtual env via [homebrew](https://formulae.brew.sh/formula/virtualenv).

### Installing with `pipx` or `pip`

1. Install `pipx` via their [installation instructions](https://pypa.github.io/pipx/) or `pip` via their [installation instructions](https://pip.pypa.io/en/stable/cli/pip_install/).

2. Install **`ape`** via `pipx install eth-ape` or `pip install eth-ape`.

### Installing with `docker`

Ape can also run in a docker container.

Please visit our [Dockerhub](https://hub.docker.com/repository/docker/apeworx/ape) for more details on using Ape with Docker.

```bash
docker run \
  --volume $HOME/.ape:/home/harambe/.ape \
  --volume $HOME/.vvm:/home/harambe/.vvm \
  --volume $HOME/.solcx:/home/harambe/.solcx \
  --volume $PWD:/home/harambe/project \
  apeworx/ape compile
```

## Quickstart

After you have installed Ape, run `ape --version` to verify the installation was successful.

Interact with Ape using either the [CLI](https://docs.apeworx.io/ape/latest/index.html) or [Python code](https://docs.apeworx.io/ape/latest/index.html).

See the following user-guides for more in-depth tutorials:

- [Accounts][accounts-guide]
- [Networks][networks-guide]
- [Projects][projects-guide]
- [Compiling][compile-guide]
- [Testing][testing-guide]
- [Console][console-guide]
- [Scripting][scripting-guide]
- [Logging][logging-guide]

## Plugin System

Ape's modular plugin system allows users to have an interoperable experience with Web3.

- Learn about **installing** plugins from following this [installing user guide](https://docs.apeworx.io/ape/stable/userguides/installing_plugins.html).

- Learn more about **developing** your own plugins from this [developing user guide](https://docs.apeworx.io/ape/stable/userguides/developing_plugins.html).

**NOTE**: If a plugin does not originate from the [ApeWorX GitHub Organization](https://github.com/ApeWorX?q=ape&type=all), you will get a warning about installing 3rd-party plugins.
Install 3rd party plugins at your own risk.

[accounts-guide]: https://docs.apeworx.io/ape/stable/userguides/accounts.html
[actions-badge]: https://github.com/ApeWorX/ape/actions/workflows/test.yaml/badge.svg
[actions-url]: https://github.com/ApeWorX/ape/actions?query=branch%3Amain+event%3Apush
[compile-guide]: https://docs.apeworx.io/ape/stable/userguides/compile.html
[console-guide]: https://docs.apeworx.io/ape/stable/userguides/console.html
[discord-badge]: https://img.shields.io/discord/922917176040640612.svg?logo=discord&style=flat-square
[discord-url]: https://discord.gg/apeworx
[licence-badge]: https://img.shields.io/github/license/ApeWorX/ape?color=blue
[licence-url]: https://github.com/ApeWorX/ape/blob/main/LICENSE
[logging-guide]: https://docs.apeworx.io/ape/stable/userguides/logging.html
[networks-guide]: https://docs.apeworx.io/ape/stable/userguides/networks.html
[projects-guide]: https://docs.apeworx.io/ape/stable/userguides/projects.html
[pypi-badge]: https://img.shields.io/pypi/dm/eth-ape?label=pypi.org
[pypi-url]: https://pypi.org/project/eth-ape/
[scripting-guide]: https://docs.apeworx.io/ape/stable/userguides/scripts.html
[testing-guide]: https://docs.apeworx.io/ape/stable/userguides/testing.html
[twitter-badge]: https://img.shields.io/twitter/follow/ApeFramework
[twitter-url]: https://twitter.com/ApeFramework
