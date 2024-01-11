# Networks

When interacting with a blockchain, you will have to select an ecosystem (e.g. Ethereum, Arbitrum, or Fantom), a network (e.g. Mainnet or Goerli) and a provider (e.g. Eth-Tester, Geth, or Alchemy).
Networks are part of ecosystems and typically defined in plugins.
For example, the `ape-ethereum` plugin comes with Ape and can be used for handling EVM-like behavior.

## Selecting a Network

Before discussing how to add custom networks or install L2 network plugins, you need to know how to specify the network choice.
No matter what type of network you are using in Ape, you specify the network using a "network choice" triplet value:

```python
"<ecosystem-name>:<network-name>:<provider-name>"
```

Where `ecosystem-name` refers to the ecosystem, e.g. `ethereum`, `polygon`, `fantom`, or any valid ecosystem plugin name.
The `network-name` refers to a network such as `mainnet`, `local`, or something else defined by your ecosystem or custom network config.
And `provider-name` refers to the provider plugin in Ape, such as `geth` for a generic node or `foundry` if the network is more Anvil-based, or a different plugin altogether.

Commonly, the network triplet value is specified via the `--network` option in Ape CLI commands.
The following is a list of common Ape commands that can use the `--network` option:

```bash
ape test --network ethereum:local:foundry
ape console --network arbitrum:testnet:alchemy # NOTICE: All networks, even from other ecosystems, use this.
```

To see all possible values for `--network`, run the command:

```shell
ape networks list
```

You can also use the `--network` option on scripts that use the `main()` method approach or scripts that implement that `ConnectedProviderCommand` command type.
See [the scripting guide](./scripts.html) to learn more about scripts and how to add the network option.

Also, you can omit values to use defaults.
For example, the default ecosystem is `ethereum` and the default network is `local`, so you can do:

```bash
ape run <custom-cmd> --network ::foundry
```

as a short-cut for `ethereum:local:foundry`.
(note: `<custom-command>` refers to the name of a script that uses the network option or is a `ConnectedProviderCommand`.
See the [scripting guide](./scripts.html) for more information).

Next, we will talk about how to add additional networks to your Ape environment.

## L2 Networks

Common L2 networks, such as Arbitrum, Polygon, Optimism, or Fantom, have ApeWorX-maintained (trusted) plugins that override the Ethereum ecosystem API class and change any defaults that are needed.
You can install these plugins by doing:

```shell
ape plugins install arbitrum polygon optimism fantom
```

Each plugin does different things.
In general, L2 plugins are very small and override the Ethereum ecosystem class.
Here are some examples of changes L2 plugins make that allow improved support for these networks:

1. Networks that don't support EIP-1559 transactions use Static-fee transaction types by default whereas `ape-ethereum` will use EIP-1559 transactions by default.
2. Some networks, such as `ape-arbitrum`, have unique transaction types (and receipt types!) that are handled in the plugin.
   This logic does not have to live in the base `ape-ethereum` plugin but can live in the network's custom plugin.
3. Fee token information: When displaying gas reports or other data, network plugins can use the correct fee-token symbols, such as Polygon MATIC.

Here is a list of all L2 network plugins supported by Ape:

| Name              | GitHub Path                                                               |
| ----------------- | ------------------------------------------------------------------------- |
| ape-avalanche     | [ApeWorX/ape-avalanche](https://github.com/ApeWorX/ape-avalanche)         |
| ape-arbitrum      | [ApeWorX/ape-arbitrum](https://github.com/ApeWorX/ape-arbitrum)           |
| ape-base          | [ApeWorX/ape-base](https://github.com/ApeWorX/ape-base)                   |
| ape-fantom        | [ApeWorX/ape-fantom](https://github.com/ApeWorX/ape-fantom)               |
| ape-optmism       | [ApeWorX/ape-optimism](https://github.com/ApeWorX/ape-optimism)           |
| ape-polygon       | [ApeWorX/ape-polygon](https://github.com/ApeWorX/ape-polygon)             |
| ape-polygon-zkevm | [ApeWorX/ape-polygon-zkevm](https://github.com/ApeWorX/ape-polygon-zkevm) |

**NOTE**: If you are connecting an L2 network or any other network that does not have a plugin, you can use the custom network support, which is described in the [next section](#custom-network-connection).

Once you have the L2 network plugin installed, you can configure its node's URI by setting the values in the `geth` (default node) core plugin via your `ape-config.yaml` file:

```yaml
geth:
  <ecosystem-name>:
    <network-name>:
      uri: https://path.to.node.example.com
```

To see proper ecosystem and network names needed for configuration, run the command:

```shell
ape networks list
```

In the remainder of this guide, any example below using Ethereum, you can replace with an L2 ecosystem's name and network combination.

## Custom Network Connection

If you would like to connect to a URI using an existing ecosystem plugin, you can specify a URI in the provider-section for the `--network` option:

```bash
ape run script --network <ecosysem-name>:<network-name>:https://foo.bar
```

Additionally, if you want to connect to an unknown ecosystem or network, you can use the URI by itself.
This uses the default Ethereum ecosystem class.

```bash
ape run script --network https://foo.bar
```

**WARNING**: The recommended approach is to use an L2 plugin when one exists, as it will integrate better in the Ape ecosystem.

Here are some general reason why Network plugins are recommended:

1. You may need to integrate with other plugins, such as explorer plugins for getting contract types.
2. Some chains may not implement EIP-1559 or may have forked from a specific configuration.
3. Response differences in uncommon blocks, such as the `"pending"` block or the genesis block.
4. Revert messages and exception-handling differences.
5. You can handle chain differences such as different transaction types in Arbitrum, non-EVM chains and behaviors like Starknet.

### Configure Custom Networks

To re-use and save custom network configurations, add them to an `ape-config.yaml` file, likely in your root `$HOME/.ape` directory so networks can be used globally across projects.
Here is an example of configuring custom networks:

```yaml
networks:
  custom:
    - name: chainnet
      chain_id: 95959595959595959  # Required when using custom networks this way.
      ecosystem: polygon  # the custom network will use this ecosystem plugin for it's operation
      default_provider: geth  # Default is a generic node

# Also, configure your provider to use the right RPC URL for this network!
geth:
  polygon:
    chainnet:
      uri: https://chainnet.polygon.example.com
```

After configuring a custom network, connect as you would normally:

```shell
ape console --network polygon:chainnet:foundry
```

## Configuring Networks

Change network defaults using your project's `ape-config.yaml` file.
The following configuration changes the default ecosystem, network, and provider such that if you omitted the `--network` option on connected-provider commands, it would use the value `<ecosystem-name>:<network-name>:<provider-name>`.

```yaml
default_ecosystem: <ecosystem-name>

<ecosystem-name>:
  default_network: <network-name>
  <network-name>:
    default_provider: <provider-name>
```

As mentioned \[above\](#L2 Networks), ecosystems and networks typically come from plugins and their names and values are defined in those plugins.
The ecosystem name goes in placeholder `<ecosystem-name>` and the network names go in place for `<network-name>`.

**If you are unsure of the values to place here, run the following command**:

```shell
ape networks list
```

This command lists all the ecosystem names and networks names installed currently in Ape.
Place the identical name in the config to configure that ecosystem or network.

You may also configure a specific gas limit for a given network:

```yaml
<ecosystem-name>:
  default_network: <network-name>
  <network-name>:
    gas_limit: "max"
```

You may use one of:

- `"auto"` - gas limit is estimated for each transaction
- `"max"` - the maximum block gas limit is used
- A number or numeric string, base 10 or 16 (e.g. `1234`, `"1234"`, `0x1234`, `"0x1234"`)

For the local network configuration, the default is `"max"`. Otherwise, it is `"auto"`.

## Local Network

The default network in Ape is the local network (keyword `"local"`).
It is meant for running tests and debugging contracts.
Out-of-the-box, Ape ships with two development providers you can use for the `local` network:

- [EthTester](https://github.com/ethereum/eth-tester)
- An Ephemeral Geth process

```bash
ape test --network ::test
ape test --network ::geth  # Launch a local development geth process
```

To learn more about testing in ape, follow [this guide](./testing.html).

## Live Networks

Use the core plugin `ape-geth` to connect to local or remote nodes via URI.
The geth plugin is abstract in that it represents any node, not just geth nodes.
However, it will work best when connected to a geth node.
To configure network URIs in geth, you can use the `ape-config.yaml` file:

```yaml
geth:
  ethereum:
    mainnet:
      uri: https://foo.node.bar
```

## Running a Network Process

To run a network with a process, use the `ape networks run` command:

```shell
ape networks run
```

By default, `ape networks run` runs a development Geth process.
To use a different network, such as `hardhat` or Anvil nodes, use the `--network` flag:

```shell
ape networks run --network ethereum:local:foundry
```

## Provider Interaction

Once you are connected to a network, you now have access to a `.provider`.
The provider class is what higher level Manager classes in Ape use to interface with the blockchain.
You can call methods directly from the provider, like this:

```python
from ape import chain

block = chain.provider.get_block("latest")
```

## Provider Context Manager

Use the [ProviderContextManager](../methoddocs/api.html#ape.api.networks.ProviderContextManager) to change the network-context in Python.
When entering a network for the first time, it will connect to that network.
**You do not need to call `.connect()` or `.disconnect()` manually**.

For example, if you are using a script with a default network connection, you can change connection in the middle of the script by using the provider context manager:

```python
from ape import chain, networks

def main():
    start_provider = chain.provider.name
    with networks.ethereum.mainnet.use_provider("geth") as provider:
        # We are using a different provider than the one we started with.
        assert start_provider != provider.name
```

Jump between networks to simulate multi-chain behavior.

```python
import click
from ape import networks

@click.command()
def cli():
    with networks.polygon.mainnet.use_provider("geth"):
        ...
    with networks.ethereum.mainnet.use_provider("geth"):
        ...
```

The argument to [use_provider()](../methoddocs/api.html#ape.api.networks.NetworkAPI.use_provider) is the name of the provider you want to use.
You can also tell Ape to use the default provider by calling method [use_default_provider()](../methoddocs/api.html#ape.api.networks.NetworkAPI.use_default_provider) instead.
This will use whatever provider is set as default for your ecosystem / network combination (via one of your `ape-config.yaml` files).

For example, let's say I have a default provider set like this:

```yaml
arbitrum:
  mainnet:
    default_provider: alchemy
```

```python
import ape

# Use the provider configured as the default for the arbitrum::mainnet network.
# In this case, it will use the "alchemy" provider.
with ape.networks.arbitrum.mainnet.use_default_provider():
    ...
```

You can also use the [parse_network_choice()](../methoddocs/managers.html#ape.managers.networks.NetworkManager.parse_network_choice) method when working with network choice strings:

```python
from ape import networks

# Same as doing `networks.ethereum.local.use_provider("test")`.
with networks.parse_network_choice("ethereum:local:test") as provider:
    print(provider)
```

**A note about disconnect**: Providers do not disconnect until the very end of your Python session.
This is so you can easily switch network contexts in a bridge or multi-chain environment, which happens in fixtures and other sessions out of Ape's control.
However, sometimes you may definitely want your temporary network session to end before continuing, in which case you can use the `disconnect_after=True` kwarg:

```python
from ape import networks

with networks.parse_network_choice("ethereum:local:foundry", disconnect_after=True) as provider:
    print(provider)
```

### Forked Context

Using the `networks.fork()` method, you can achieve similar effects to using a forked network with `disconnect_after=True`.
For example, let's say we are running the following script on the network `ethereum:mainnet`.
We can switch to a forked network by doing this:

```python
from ape import networks

def main():
    with networks.fork("foundry"):
        ...
        # Do stuff on a local, forked version of mainnet

    # Switch back to mainnet.
```
