# Ape Framework

Ape is a framework for Web3 Python applications and smart contracts, with advanced functionality for testing, deployment, and on-chain interactions.

See [website](https://apeworx.io/) and [documentation](https://docs.apeworx.io/ape).

## Dependencies

* [python3](https://www.python.org/downloads) version 3.7 or greater, python3-dev

## Installation

### via `pip`

You can install the latest release via [`pip`](https://pypi.org/project/pip/):

```bash
pip install eth-ape
```

### via `setuptools`

You can clone the repository and use [`setuptools`](https://github.com/pypa/setuptools) for the most up-to-date version:

```bash
git clone https://github.com/ApeWorX/ape.git
cd ape
python3 setup.py install
```

### via `docker`

Please visit our [Dockerhub](https://hub.docker.com/repository/docker/apeworx/ape) for more details on using Ape with Docker.

example commands:  

compiling:
```
docker run \
--volume $HOME/.ape:/root/.ape \
--volume $HOME/.vvm:/root/.vvm \
--volume $HOME/.solcx:/root/.solcx \
--volume $PWD:/root/project \
--workdir /root/project \
apeworx/ape compile
```

running the ape console:
```
docker run -it \
--volume $HOME/.ape:/root/.ape \
--volume $HOME/.vvm:/root/.vvm \
--volume $HOME/.solcx:/root/.solcx \
--volume $PWD:/root/project \
--workdir /root/project \
apeworx/ape console
```

## Quick Usage

Ape is primarily meant to be used as a command line tool. Here are some things you can use ape to do:

```bash
# Work with your accounts
$ ape accounts list

# Compile your project's smart contracts
$ ape compile --size

# Run your tests with pytest
$ ape test -k test_only_one_thing --coverage --gas

# Connect an IPython session through your favorite provider
$ ape console --network ethereum:mainnet:infura

# Add new plugins to ape
$ ape plugins install plugin-name
```

Ape also works as a package. You can use the same networks, accounts, and projects from the ape package as you can in the cli:

```python
# Work with registered networks, providers, and blockchain ecosystems (like Ethereum)
from ape import networks
with networks.ethereum.mainnet.use_provider("infura"):
    ...  # Work with the infura provider here

# Work with test accounts, local accounts, and (WIP) popular hardware wallets
from ape import accounts
a = accounts[0]  # Load by index
a = accounts.test_accounts[0] # Load test account by index
a = accounts["example.eth"]  # or load by ENS/address
a = accounts.load("alias") # or load by alias

# Work with contract types
from ape import project
c = a.deploy(project.MyContract, ...)
c.viewThis()  # Make Web3 calls
c.doThat(sender=a)  # Make Web3 transactions
assert c.MyEvent[-1].caller == a  # Search through Web3 events
```

## Development

This project is in development and should be considered a beta.
Things might not be in their final state and breaking changes may occur.
Comments, questions, criticisms and pull requests are welcomed.

## Documentation

To build docs:

```bash
python build_docs.py
```

## License

This project is licensed under the [Apache 2.0](LICENSE).
