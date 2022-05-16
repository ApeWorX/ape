# Quick Start

## Prerequisite

In the latest release, Ape requires:

-   Linux or macOS
-   Python 3.7.X or later

**Windows**:

1.  Install Windows Subsystem Linux
    [(WSL)](https://docs.microsoft.com/en-us/windows/wsl/install)
2.  Choose Ubuntu 20.04 OR Any other Linux Distribution with Python
    3.7.X or later

Please make sure you are using Python 3.7.X or later.

Check your python command by entering

```bash
python3 --version
```

## Installation

**Suggestion**: Create a virtual environment using `virtualenv` or `venv.`

You may skip this creating a virtual environment if you know you don\'t
require one for your use case.

* [virtualenv](https://pypi.org/project/virtualenv/)
* [venv](https://docs.python.org/3/library/venv.html)

Create your virtual environment folder

```bash
python3 -m venv /path/to/new/environment
source <venv_folder>/bin/activate
```

You should see `(name_of_venv) DESKTOP_NAME:~/path:$`.
To deactivate the virtual environment, do:

```bash
deactivate
```

Now that your Python version is later than 3.7.X and you have created a
virtual environment. Let\'s install Ape! There are 3 ways to install
ape: `pip`, `setuptools`, or `Docker`.

### via `pip`

You can install the latest release via
[pip](https://pypi.org/project/pip/):

```bash
pip install -U pip
pip install eth-ape
```

or install w/ ApeWorX-recommended plugins via

```bash
pip install eth-ape[recommended-plugins]
```

### via `docker`

Please visit our
[Dockerhub](https://hub.docker.com/repository/docker/apeworx/ape) for
more details on using Ape with Docker.

```bash
docker run \
--volume $HOME/.ape:/root/.ape \
--volume $HOME/.vvm:/root/.vvm \
--volume $HOME/.solcx:/root/.solcx \
--volume $PWD:/root/project \
--workdir /root/project \
apeworx/ape compile
```

**Docker Uninstall Process:** You will need to remove files generated by
docker

```bash
sudo rm -rf **\~/.solcx**
sudo rm -rf **\~/.vvm**
```

## Overview

For more in-depth information about the project please look at the [projects](~/userguides/project.md)
It explains the purpose of each folder and how to use them effectively.

Use `ape init` to initialize your ape project folders. Visit [userguide project](~/userguide/project.md) for more information.  

```bash
ape init
```

## Environment Variables:

Environment Variables are used to help connect you to your files or ecosystems outside of ApeWorX.

Please setup environment variables (where applicable) and follow the latest instructions from the 3rd party:

Example use case:

```bash
# Used by the `ape-infura` plugin
export WEB3_INFURA_PROJECT_ID=<YOUR_INFURA_PROJECT_ID>
# Used by the `ape-alchemy` plugin
export WEB3_ALCHEMY_API_KEY=<YOUR_ALCHEMY_KEY>
```

Visit [ape-alchemy](https://github.com/ApeWorX/ape-alchemy/blob/main/README.md#quick-usage)

Visit [ape-infura](https://github.com/ApeWorX/ape-infura#readme)

## Ape Console

Ape provides an IPython interactive console with useful pre-defined locals to interact with your project.
To interact with a deployed contract in a local environment, start by opening the console:

```bash
ape console --network :mainnet-fork:hardhat
```

Visit [Ape Console](https://docs.apeworx.io/ape/stable/commands/console.html) to learn how to use Ape Console.

## Quick Usage

Use `-h` to list all the commands.

```bash
ape -h
```

You can import or generate accounts.

```bash
ape accounts import acc0   # Will prompt for a private key
ape accounts generate acc1
````

List all your accounts with the `list` command.

```bash
ape accounts list
```

Add any plugins you may need, such as `vyper`.

```bash
ape plugins list -a
ape plugins install vyper
ape plugins list -a
```

**NOTE**: If a plugin does not originate from the 
[ApeWorX GitHub organization](https://github.com/ApeWorX?q=ape&type=all), you will get a warning about installing 
3rd-class plugins. Any plugin that is not an official plugin has the chance of not being trustworthy. Thus, you should 
be mindful about which plugins you install. Additionally, plugins that come bundled with `ape` in the core installation 
cannot be removed and are considered part of the `ape` core software.

You can interact and compile contracts.
Here is an example of a project with a contract you interact with: 

```bash 
git clone https://github.com/brownie-mix/vyper-token-mix.git
cd vyper-token-mix/
```

You can compile contracts within the `contracts/` directory of your project.
The `--size` option will display you the size of the contract.

```bash
ape compile --size
```

Provide the same arguments to `pytest` as you would to the `ape test` command.

```bash
ape test -k test_only_one_thing --coverage
```

Connect an IPython session through your favorite provider.

```bash
ape console --network ethereum:mainnet:infura
```

If you want to run specific files in a `scripts/` directory, you can do it using the `ape run` command.

```bash
# This command will run a file named deploy in the scripts/ directory
$ ape run deploy
```

### Logging

To enable debug logging, run your command with the `--verbosity` flag using `DEBUG` as the value:

```bash
ape run --verbosity DEBUG
```

You can use `ape` as a package outside of scripts for the `ape run` command as well.

You can work with registered networks, providers, and blockchain ecosystems (like Ethereum):

```python
from ape import networks
with networks.ethereum.mainnet.use_provider("infura"):
    ...  # Work with the infura provider here
```

You can work with test accounts, local accounts, and (WIP) popular hardware wallets:

```python
from ape import accounts
a = accounts[0]  # Load by index
a = accounts["example.eth"]  # or load by ENS/address
a = accounts.load("alias") # or load by alias
```

You can also work with contract types:

```python
from ape import project
c = a.deploy(project.MyContract, ...)
c.viewThis()  # Make Web3 calls
c.doThat(sender=a)  # Make Web3 transactions
assert c.MyEvent[-1].caller == a  # Search through Web3 events
```
