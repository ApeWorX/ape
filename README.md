# Overview

**Ape Framework** is an easy-to-use Web3 development tool.
Users can compile, test, and interact with smart contracts all in one command line session.
With our **modular plugin system**, Ape supports multiple contract languages and chains.

Ape is built by [ApeWorX LTD](https://www.apeworx.io/).

Join our [ApeWorX Discord server](https://discord.gg/apeworx) to stay up to date on new releases, plugins and tutorials.

If you want to just get started, jump down to the [Playing with Ape](#playing-with-ape)

## Documentation

Read our [technical documentation](https://docs.apeworx.io/ape/stable/) to get a deeper understanding of our open source Framework.

Read our [academic platform](https://academy.apeworx.io/) will help you master Ape Framework with tutorials and challenges.

## Prerequisite

In the latest release, Ape requires:

- Linux or macOS
- Python 3.8 or later
- **Windows**: Install Windows Subsystem Linux [(WSL)](https://docs.microsoft.com/en-us/windows/wsl/install) with Python 3.8 or later

Check your python version in a terminal with `python3 --version`

## Installation

There are three ways to install ape: `pipx`, `pip`, or `Docker`.

### Considerations for Installing:

- We advise installing in a [virtualenv](https://pypi.org/project/virtualenv/) or [venv](https://docs.python.org/3/library/venv.html) to avoid interfering with *OS-level site packages*.

- We advise installing **`ape`** with recommended plugins `pip install eth-ape'[recommended-plugins]'`

- We advise for **macOS** users to install virtual env via [homebrew](https://formulae.brew.sh/formula/virtualenv)

### via `pipx` or `pip`

1. Install `pipx` via their [installation instructions](https://pypa.github.io/pipx/) or `pip` via their [installation instructions](https://pip.pypa.io/en/stable/cli/pip_install/)

2. Install **`ape`** via `pipx install eth-ape` or `pip install eth-ape`

### via `docker`

Ape can also run in a docker container.

Please visit our [Dockerhub](https://hub.docker.com/repository/docker/apeworx/ape) for more details on using Ape with Docker.

```bash
docker run \
--volume $HOME/.ape:/home/harambe/.ape \
--volume $HOME/.vvm:/home/harambe/.vvm \
--volume $HOME/.solcx:/home/harambe/.solcx \
--volume $PWD:/home/harambe/project \
--workdir /home/harambe/project \
apeworx/ape compile
```

## Playing with Ape

After you installed Ape, you can run `ape --version` to make sure it works and is the latest version.

There are two ways to interact with Ape:

- [CLI Reference](https://docs.apeworx.io/ape/latest/index.html)

- [Python Reference](https://docs.apeworx.io/ape/latest/index.html)

Ape is both a CLI tool and a Python SDK.

The CLI tool contains all the Ape commands and the Python SDK contains the classes and types needed to compose scripts, console actions, and tests.

## **Ape Modular Plugin System:**

Our [list of plugins](https://www.apeworx.io/#plugins) is the best way to have the most interoperable experience with Web3.

**NOTE**: If a plugin does not originate from the [ApeWorX GitHub Organization](https://github.com/ApeWorX?q=ape&type=all), you will get a warning about installing 3rd-party plugins.

Install 3rd party plugins at your own risk.

Additionally, plugins that come bundled with **`ape`** in the core installation cannot be removed and are part of the **`ape`** core software.

- Learn more about **installing** plugins from following this [installing user guide](https://docs.apeworx.io/ape/stable/userguides/installing_plugins.html).

- Learn more about **developing** your own plugins from this [developing user guide](https://docs.apeworx.io/ape/stable/userguides/developing_plugins.html).

### Accounts

In Ape, you will need accounts to make transactions.
You can import or generate accounts using the core `accounts` plugin:

```bash
ape accounts import acc0   # Will prompt for a private key
ape accounts generate acc1
```

List all your accounts with the `list` command.

```bash
ape accounts list
```

Learn more about accounts in Ape by following the [accounts guide](https://docs.apeworx.io/ape/stable/userguides/accounts.html).

### Plugins

Add any plugins you may need, such as `vyper`.

```bash
ape plugins list -a
ape plugins install vyper
ape plugins list -a
```

## Projects

When using Ape, you generally will work with a project.

Learn more about smart-contract **projects** from this [projects guide](https://docs.apeworx.io/ape/stable/userguides/projects.html).

### Compiling

You can compile contracts within the `contracts/` directory of your project.
The `--size` option will display you the size of the contract.

```bash
ape compile --size
```

Learn more about compiling in Ape by following the [compile guide](https://docs.apeworx.io/ape/stable/userguides/compile.html).

### Testing

Use Ape to test your smart-contract projects.
Provide the same arguments to `pytest` as you would to the `ape test` command.

For example:

```bash
ape test -k test_only_one_thing
```

Visit the [testing guide](https://docs.apeworx.io/ape/stable/userguides/testing.html) to learn more about testing using Ape.

### Console

Ape provides an `IPython` interactive console with useful pre-defined locals to interact with your project.
To interact with a deployed contract in a local environment, start by opening the console:

```bash
ape console --network ethereum:mainnet:infura
```

Visit [Ape Console](https://docs.apeworx.io/ape/stable/commands/console.html) to learn how to use Ape Console.

### Scripts

If you want to run specific files in a `scripts/` directory, you can do it using the `ape run` command.

```bash
# This command will run a file named deploy in the scripts/ directory
$ ape run deploy
```

Learn more about scripting using Ape by following the [scripting guide](https://docs.apeworx.io/ape/stable/userguides/scripts.html).

### Logging

To enable debug logging, run your command with the `--verbosity` flag using `DEBUG` as the value:

```bash
ape --verbosity DEBUG run
```

### Networks

You can work with registered networks, providers, and blockchain ecosystems (like Ethereum):

```python
from ape import networks
with networks.ethereum.mainnet.use_provider("infura"):
    ...  # Work with the infura provider here
```

To learn more about networks in Ape, see [this guide](https://docs.apeworx.io/ape/stable/commands/networks.html).
