# Scripting

You can write scripts that run using the `ape run` command.
The `ape run` command will register and run Python files defined under the `scripts/` directory that do not start with an `_` underscore.

## CLI Scripts

Place scripts in your project's `scripts/` directory.
Follow [this guide](./projects.html) to learn more about the Ape project structure.
If your scripts take advantage of utilities from our [`ape.cli`](../methoddocs/cli.html#ape-cli) submodule, you can build a [Click](https://click.palletsprojects.com/) command line interface by defining a `click.Command` or `click.Group` object called `cli` in your file:
Follow [this guide](./clis.html) to learn more about what you can do with the utilities found in `ape.cli`.

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

```{note}
By default, `cli` scripts do not have [`ape.cli.network_option`](../methoddocs/cli.html?highlight=options#ape.cli.options.network_option) installed, giving you more flexibility in how you define your scripts.
```

However, you can add the `network_option` or `ConnectedProviderCommand` to your scripts by importing them from the `ape.cli` namespace:

```python
import click
from ape.cli import ConnectedProviderCommand


@click.command(cls=ConnectedProviderCommand)
def cli(ecosystem, network, provider):
    click.echo(f"Connected to {ecosystem.name}:{network.name} using provider '{provider.name}'.")
    
    # Access chain and other managers automatically
    from ape import chain
    click.echo(f"Current block: {chain.blocks.height}")

@click.command(cls=ConnectedProviderCommand)
def cli(network, provider):
    click.echo(f"You are connected to network '{network.name}'.")
    click.echo(provider.chain_id)
    
```

## Multi-Network Commands

Scripts can use the context manager for multi-network functionality.
Here's an example of using a multi-network pattern in a script:

```python
import click
from ape import networks, chain, accounts
from ape.cli import network_option


@click.command()
@network_option()
def cli():
    """Connect to multiple networks in one command."""
    # Uses the provider from network_option
    account = accounts.load("my-account")
    balance1 = account.balance
    network1 = chain.provider.network.name
    
    print(f"Balance on {network1}: {balance1}")
    
    # Temporarily use a different provider than was selected originally
    with networks.ethereum.sepolia.use_provider("alchemy"):
        balance2 = account.balance  # Balance on Sepolia
        network2 = chain.provider.network.name
        print(f"Balance on {network2}: {balance2}")
        
        # Can even do a third network
        with networks.arbitrum.mainnet.use_provider("infura"):
            balance3 = account.balance  # Balance on Arbitrum
            network3 = chain.provider.network.name
            print(f"Balance on {network3}: {balance3}")
    
    # Back to the original network
    print(f"Back to {network1}")
```

This pattern is especially useful for cross-chain operations, data gathering from multiple networks, or comparing state between networks.

@click.command(cls=ConnectedProviderCommand)
def cli_2():
click.echo(f"Using any network-based argument is completely optional.")

````

Assume we saved this script as `shownet.py` and have the [ape-alchemy](https://github.com/ApeWorX/ape-alchemy) plugin installed.
Try changing the network using the `--network` option:

```bash
ape run shownet --network ethereum:mainnet:alchemy
````

### Multi-network Scripting

Because CLI-based scripts do not automatically connect to the provider before executing, they are ideal for multi-chain use-cases because they allow you to delay and manage the connection(s).
To learn more about how to control the network-context in Ape Pythonically, see [this guide](https://docs.apeworx.io/ape/stable/userguides/networks.html#provider-context-manager).

Here is an example of a multi-chain script:

```python
import click
from ape.cli import ape_cli_context

@click.command()
@ape_cli_context()
def cli(cli_ctx):
    # There is no connection yet at this point.
    testnets = {
        "ethereum": ["sepolia"],
        "polygon": ["amoy"]
    }
    nm = cli_ctx.network_manager

    for ecosystem_name, networks in testnets.items():
        ecosystem = nm.ecosystems[ecosystem_name]

        for network_name in networks:
            # Start making connections.
            network = ecosystem.get_network(network_name)

            with network.use_provider("alchemy") as provider:
                print(f"Connected to {provider.network_choice}")
```

Things to notice:

1. It uses the CLI approach _without_ `cls=ConnectedProviderCommand`; thus it is not connected before it makes the first call to `.use_provider("alchemy")`.
2. It uses the `@ape_cli_context()` decorator to get access to Ape instances such as the `network_manager`.
3. Each network is only active during the context, thus allowing you to switch contexts and control chain-hopping in scripts.
4. **You do not need to call `.connect()` on the provider yourself!**

## Main Method Scripts

You can also use the main-method approach when defining scripts.
To do this, define a method named `main()` in your script:

```python
def main():
    print("Hello world!")
```

```{note}
main-method scripts will always provide a `--network` option and run in a connected-context.
Therefore, they are not ideal for multi-chain scripts.
`main`-method scripts work best for quick, single-network, connection-based workflows.
```

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

Suppose the name of the script is `foobar`, you can run it via:

```shell
ape run foobar
```

Without specifying `--network`, the script will connect to your default network.
Else, specify the network using the `--network` flag:

```shell
ape run foobar --network polygon:amoy:alchemy
```

You can also change networks within the script using the `ProviderContextManager` (see examples in the CLI-script section above).
For multi-chain use-cases, we recommend sticking to the CLI based scripts to avoid the initial connection `main`-method scripts make.
