# Scripting

You can write scripts that run using the `ape run` command.
The `ape run` command will register and run Python files defined under the `scripts/` directory that do not start with an `_` underscore.

## CLI Scripts

Place scripts in your project's `scripts/` directory.
Follow [this guide](./projects.html) to learn more about the Ape project structure.
If your scripts take advantage of utilities from our [`ape.cli`](../methoddocs/cli.html#ape-cli) submodule, you can build a [Click](https://click.palletsprojects.com/) command line interface by defining a `click.Command` or `click.Group` object called `cli` in your file:

```python
import click

@click.command()
def cli():
    print("Hello world!")
```

Assume we named the script `helloworld.py`.
To execute the script, run the following:

```bash
ape run helloworld
```

You can also execute scripts in subdirectories.
For example, assuming we have script `<project>/scripts/hello/helloworld.py`, we would execute it by running:

```bash
ape run hello helloworld
```

Note that by default, `cli` scripts do not have [`ape.cli.network_option`](../methoddocs/cli.html?highlight=options#ape.cli.options.network_option) installed, giving you more flexibility in how you define your scripts.
However, you can add the `network_option` to your scripts by importing both the `NetworkBoundCommand` and the `network_option` from the `ape.cli` namespace:

```python
import click
from ape.cli import network_option, NetworkBoundCommand


@click.command(cls=NetworkBoundCommand)
@network_option()
def cli(network):
    click.echo(f"You are connected to network '{network}'.")
```

Assume we saved this script as `shownet.py` and have the [ape-alchemy](https://github.com/ApeWorX/ape-alchemy) plugin installed.
Try changing the network using the `--network` option:

```bash
ape run shownet --network ethereum:mainnet:alchemy
```

## Main Method Scripts

You can also use the main-method approach when defining scripts.
To do this, define a method named `main()` in your script:

```python
def main():
    print("Hello world!")
```

**NOTE**: main-method scripts will always provide a network option to the call and thus will always connect to a network.

To demonstrate, use the following script:

```python
from ape import networks
import click


def main():
    ecosystem_name = networks.provider.network.ecosystem.name
    network_name = networks.provider.network.name
    provider_name = networks.provider.name
    click.echo(f"You are connected to network '{ecosystem_name}:{network_name}:{provider_name}'.")
```
