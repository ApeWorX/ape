# Quick Start

## Prerequisite

In the latest release, Ape requires:

- Linux or macOS
- Python 3.8 or later

**Windows**:

1.  Install Windows Subsystem Linux
    [(WSL)](https://docs.microsoft.com/en-us/windows/wsl/install)
2.  Choose Ubuntu 20.04 OR Any other Linux Distribution with Python
    3.8 or later

Check your python command by entering:

```bash
python3 --version
```

## Installation

There are 3 ways to install ape: `pipx`, `pip`, or `Docker`.

### via `pipx`

Install `pipx` via their [installation instructions](https://pypa.github.io/pipx/)

Then install `ape` via

```bash
pipx install eth-ape
```

To install Ape and a list of common, recommended plugins at the same time, do:

```bash
pip install eth-ape'[recommended-plugins]'
```

### via `pip`

**Suggestion**: Create a virtual environment using `virtualenv` or `venv.`

You may skip this creating a virtual environment if you know you don\'t require one for your use case.

- [virtualenv](https://pypi.org/project/virtualenv/)
- [venv](https://docs.python.org/3/library/venv.html)

**NOTE**: For MacOS users, we advise installing in a virtual environment to avoid interfering with OS-level site packages.

### virtualenv via `homebrew`

* (MacOS Option) Install via homebrew [brew](https://formulae.brew.sh/formula/virtualenv)

First, create your virtual environment folder:

```bash
python3 -m venv <path/to/new/env>
```

Then, activate your virtual environment:

```bash
source <venv_folder>/bin/activate
```

You should see `(name_of_venv) DESKTOP_NAME:~/path:$`.

To deactivate the virtual environment, do:

```bash
deactivate
```

Now that you have Python installed in your virtual environment, we may install Ape:
You can install the latest release via [pip](https://pypi.org/project/pip/):

```bash
pip install -U pip
pip install eth-ape
```

To install Ape and a list of common, recommended plugins at the same time, do:

```bash
pip install eth-ape'[recommended-plugins]'
```

### via `docker`

Please visit our [Dockerhub](https://hub.docker.com/repository/docker/apeworx/ape) for more details on using Ape with Docker.

```bash
docker run \
--volume $HOME/.ape:/root/.ape \
--volume $HOME/.vvm:/root/.vvm \
--volume $HOME/.solcx:/root/.solcx \
--volume $PWD:/root/project \
--workdir /root/project \
apeworx/ape compile
```

**Docker Uninstall Process:** You will need to remove files generated by docker

```bash
sudo rm -rf **\~/.solcx**
sudo rm -rf **\~/.vvm**
```

## Environment Variables:

Some plugins require environment variables to connect to their external systems, such project IDs or API keys.
Follow instructions from individual plugin documentations, such as:

* [ape-alchemy](https://github.com/ApeWorX/ape-alchemy/blob/main/README.md#quick-usage)
* [ape-infura](https://github.com/ApeWorX/ape-infura#readme)

Generally, set environment variables by doing the following:

```bash
# Used by the `ape-infura` plugin
export WEB3_INFURA_PROJECT_ID=<YOUR_INFURA_PROJECT_ID>
# Used by the `ape-alchemy` plugin
export WEB3_ALCHEMY_API_KEY=<YOUR_ALCHEMY_KEY>
```

Place these in environment files, such as your `.bashrc` or `.zshrc`.

## Quick Usage

Use `-h` to list all the commands:

```bash
ape -h
```

### Projects

When using Ape, you generally will work with a project.
To quickly get started using ape, generate a project using the `ape init` command:

```bash
ape init
```

For more in-depth information about smart-contract projects using the Ape framework, see the [projects guide](https://docs.apeworx.io/ape/stable/userguides/projects.html).

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

**NOTE**: If a plugin does not originate from the [ApeWorX GitHub organization](https://github.com/ApeWorX?q=ape&type=all), you will get a warning about installing 3rd-party plugins.
Install 3rd party plugins at your own risk.
Additionally, plugins that come bundled with `ape` in the core installation cannot be removed and are part of the `ape` core software.

Learn more about installing plugins from following [this guide](https://docs.apeworx.io/ape/stable/userguides/installing_plugins.html).
Learn more about developing your own plugins from [this guide](https://docs.apeworx.io/ape/stable/userguides/projects.html).

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
ape run --verbosity DEBUG
```

### Networks

You can work with registered networks, providers, and blockchain ecosystems (like Ethereum):

```python
from ape import networks
with networks.ethereum.mainnet.use_provider("infura"):
    ...  # Work with the infura provider here
```

To learn more about networks in Ape, see [this guide](https://docs.apeworx.io/ape/stable/commands/networks.html). 
