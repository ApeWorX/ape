# Networks

When interacting with a blockchain, you will have to select an ecosystem (e.g. Ethereum, Arbitrum, or Fantom), a network (e.g. Mainnet or Sepolia) and a provider (e.g. Eth-Tester, Node (Geth), or Alchemy).
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
And `provider-name` refers to the provider plugin in Ape, such as `node` for a generic node or `foundry` if the network is more Anvil-based, or a different plugin altogether.

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

| Name              | GitHub                                                                    |
| ----------------- | ------------------------------------------------------------------------- |
| ape-arbitrum      | [ApeWorX/ape-arbitrum](https://github.com/ApeWorX/ape-arbitrum)           |
| ape-avalanche     | [ApeWorX/ape-avalanche](https://github.com/ApeWorX/ape-avalanche)         |
| ape-base          | [ApeWorX/ape-base](https://github.com/ApeWorX/ape-base)                   |
| ape-blast         | [ApeWorX/ape-base](https://github.com/ApeWorX/ape-blast)                  |
| ape-bsc           | [ApeWorX/ape-base](https://github.com/ApeWorX/ape-bsc)                    |
| ape-fantom        | [ApeWorX/ape-fantom](https://github.com/ApeWorX/ape-fantom)               |
| ape-optimism      | [ApeWorX/ape-optimism](https://github.com/ApeWorX/ape-optimism)           |
| ape-polygon       | [ApeWorX/ape-polygon](https://github.com/ApeWorX/ape-polygon)             |
| ape-polygon-zkevm | [ApeWorX/ape-polygon-zkevm](https://github.com/ApeWorX/ape-polygon-zkevm) |

```{note}
If you are connecting an L2 network or any other network that does not have a plugin, you can use the custom network support, which is described in the [next section](#custom-network-connection).
```

Once you have the L2 network plugin installed, you can configure its node's URI by setting the values in the `node` core plugin via your `ape-config.yaml` file:

```yaml
node:
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

You can add custom networks to Ape without creating a plugin.
The two ways to do this are:

1. Create custom network configurations in your `ape-config.yaml` file (typically your global one).
2. Use the `--network` flag with a raw URI string.

### Custom Networks By Config

The most familiar way to use custom networks (non-plugin-based networks) in Ape is to use the `networks: custom` configuration.
Generally, you want to use the global `ape-config.yaml`, which is located in your `$HOME/.ape/` directory.
By configuring networks globally, you can share them across all your projects.
More information about configuring Ape (in general) can be found [here](./contracts.html).

To add custom networks to your `ape-config.yaml` file, follow this pattern:

```yaml
networks:
  custom:
     - name: mainnet                   # Required
       chain_id: 109                   # Required
       ecosystem: shibarium            # The ecosystem name, can either be new or an existing
       base_ecosystem_plugin: polygon  # The ecosystem base-class, defaults to the default ecosystem
       default_provider: node          # Default is the generic node provider
```

The following paragraphs explain the different parameters of the custom network config.

**name**: The `name` of the network is the same identifier you use in the network triplet for the "network" (second) section.
Read more on the network option [here](#selecting-a-network).

**chain_id**: The chain ID is required for config-based custom networks.
It ensures you are on the correct network when making transactions and is very important!

**ecosystem**: Specify your custom network's ecosystem.
This can either be an existing ecosystem or a new name entirely.
Recall, you refer to your network via the network-triplet `ecosystem:network:provider` option-str.
The ecosystem class is largely responsible for decoding and encoding data to-and-fro the blockchain but also contains all the networks.
More information about the EcosystemAPI can be found [here](../methoddocs/api.html#ape.api.networks.EcosystemAPI).
If your custom network is part of a new ecosystem, such as Shibarium, use the name of the new ecosystem, e.g. `"shibarium"`.
You may want to also adjust the `base_ecosystem_plugin` config to change the base-class used.

**base_ecosystem_plugin**: The plugin that defines the base-class to your custom ecosystem containing your custom network(s).
If your custom network's ecosystem matches closer to another L2 instead of Ethereum, use that ecosystem name as your `base_ecosystem_plugin` in your custom network config.
For example, take note that `"ethereum"` assumes EIP-1559 exists (unless configured otherwise).
If your custom network is closer to Fantom, Polygon, Avalanche, or any other L2, you may want to consider using one of those plugins as the `base_ecosystem_plugin` to your custom network.
Alternatively, you can configure your custom network the same way you configure any other network in the config (see [this section](#block-time-transaction-type-and-more-config)).

**default_provider**: The default provider is the provider class used for making the connection to your custom network, unless you specify a different provider (hence the `default_`).
Generally, you won't change this and can use the default EVM node provider.
Many provider plugins won't function here, such as `ape-infura` or `ape-alchemy`.
If you are using one of their networks, it is best to edit and use the plugins directly.
If you are using a developer-node remotely, such as a custom Anvil node, you can specify the default provider to be `foundry` instead.
However, take care in making sure you set up Foundry to correctly connect to your node.
Likewise, when using the default Ethereum node provider, you will need to tell it the RPC URL.

#### RPC URL

To configure the RPC URL for a custom network, use the configuration of the provider.
For example, if the RPC URL is `https://apenet.example.com/rpc`, configure it by doing:

```yaml
default_ecosystem: shibarium

networks:
  custom:
    - name: mainnet
      ecosystem: shibarium
      base_ecosystem_plugin: polygon  # Closest base class.
      chain_id: 109  # This must be correct or txns will fail.

node:
  shibarium:
    mainnet:
      uri: https://www.shibrpc.com
```

Now, when using `ethereum:apenet:node`, it will connect to the RPC URL `https://apenet.example.com/rpc`.

#### Forking Custom Networks

You can fork custom networks using providers that support forking, such as `ape-foundry` or `ape-hardhat`.
To fork a custom network, first ensure the custom network is set-up by following the sections above.
Once you can successfully connect to a custom network in Ape, you can fork it.

To fork the network, launch an Ape command with the `--network` option with your custom network name suffixed with `-fork` and use one of the forking providers (such as `ape-foundry`):

```
ape <cmd> --network shibarium:puppynet-fork:foundry
```

Configure the forked network in the plugin the same way you configure other forked networks:

```yaml
foundry:
  fork:
    shibarium:
      puppynet:
        block_number: 500
```

#### Explorer URL

To configure explorer URLs for your custom network, use the explorer's plugin config.
For example, let's say you added the following network:

```yaml
networks:
  custom:
    - name: customnetwork
      chain_id: 31337
      default_provider: node
```

To add a corresponding entry in `ape-etherscan` (assuming you are using `ape-etherscan` as your explorer plugin), add the following to your `ape-config.yaml` file:

```yaml
etherscan:
  ethereum:
    rate_limit: 15  # Configure a rate limit that makes sense for retry logic.

    # The name of the entry is the same as your custom network!
    customnetwork:
      uri: https://custom.scan              # URL used for showing transactions
      api_uri: https://api.custom.scan/api  # URL used for making API requests.
```

```{note}
Every explorer plugin may be different in how you configure custom networks.
Consult the plugin's README to clarify.
```

#### Block time, transaction type, and more config

Configuring network properties in Ape is the same regardless of whether it is custom or not.
As you saw above, we set the RPC URL of the custom network the same as if a plugin existed for that network.
The same is true for network config properties such as `block_time`, `default_transaction_type`, `transaction_acceptance_timeout` and more.

For example, let's say I want to change the default transaction type for the `apenet` custom network (defined in examples above).
I do this the same way as if I were changing the default transaction type on mainnet.

```yaml
ethereum:
  apenet:
    default_transaction_type: 0  # Use static-fee transactions for my custom network!
```

For a full list of network configurations like this (for both custom and plugin-based networks), [see this section](#configuring-networks).

```{note}
This also works if configuring a custom ecosystem.
```

If using a custom ecosystem, use the custom ecosystem name as the top-level config key instead:

```yaml
networks:
  custom:
    - name: mainnet
      ecosystem: shibarium
      base_ecosystem_plugin: polygon  # Closest base class.
      chain_id: 109  # This must be correct or txns will fail.

shibarium:
  mainnet:
    default_transaction_type: 0  # Use static-fee transactions for Shibarium.
```

### Custom Networks by CLI

Ape also lets you connect to custom networks on-the-fly!
If you would like to connect to a URI using an existing ecosystem plugin, you can specify a URI in the provider-section for the `--network` option:

```bash
ape run script --network <ecosystem-name>:<network-name>:https://foo.bar
```

Additionally, if you want to connect to an unknown ecosystem or network, you can use the URI by itself.
This uses the default Ethereum ecosystem class.

```bash
ape run script --network https://foo.bar
```

```{warning}
The recommended approach is to use an L2 plugin when one exists, as it will integrate better in the Ape ecosystem.
```

Here are some general reason why Network plugins are recommended:

1. You may need to integrate with other plugins, such as explorer plugins for getting contract types.
2. Some chains may not implement EIP-1559 or may have forked from a specific configuration.
3. Response differences in uncommon blocks, such as the `"pending"` block or the genesis block.
4. Revert messages and exception-handling differences.
5. You can handle chain differences such as different transaction types in Arbitrum, non-EVM chains and behaviors like Starknet.

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

As mentioned [above](#l2-networks), ecosystems and networks typically come from plugins and their names and values are defined in those plugins.
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

## Request Headers

There are several layers of request-header configuration.
They get merged into each-other in this order, with the exception being `User-Agent`, which has an append-behavior.

- Default Ape headers (includes `User-Agent`)
- Top-level configuration for headers (using `request_headers:` key)
- Per-ecosystem configuration
- Per-network configuration
- Per-provider configuration

Use the top-level `request_headers:` config to specify headers for every request.
Use ecosystem-level specification for only requests made when connected to that ecosystem.
Network and provider configurations work similarly; they are only used when connecting to that network or provider.

Here is an example using each layer:

```yaml
request_headers:
  Top-Level: "UseThisOnEveryRequest"

ethereum:
  request_headers:
    Ecosystem-Level: "UseThisOnEveryEthereumRequest"
  
  mainnet:
    request_headers:
      Network-Level: "UseThisOnAllRequestsToEthereumMainnet"

node:
  request_headers:
    Provider-Level: "UseThisOnAllRequestsUsingNodeProvider"
```

When using `User-Agent`, it will not override Ape's default `User-Agent` nor will each layer override each-other's.
Instead, they are carefully appended to each other, allowing you to have a very customizable `User-Agent`.

## Local Network

The default network in Ape is the local network (keyword `"local"`).
It is meant for running tests and debugging contracts.
Out-of-the-box, Ape ships with two development providers you can use for the `local` network:

- [EthTester](https://github.com/ethereum/eth-tester)
- An Ephemeral Node (defaults to Geth) process

```bash
ape test --network ::test
ape test --network ::node  # Launch a local development node (geth) process
```

To learn more about testing in ape, follow [this guide](./testing.html).

## Live Networks

Use the core plugin `ape-node` to connect to local or remote nodes via URI.
The node plugin is abstract in that it represents any node.
However, it will work best when connected to a geth node.
To configure network URIs in `node`, you can use the `ape-config.yaml` file:

```yaml
node:
  # When managing or running a node, configure an IPC path globally (optional)
  ipc_path: path/to/geth.ipc

  ethereum:
    mainnet:
      # For `uri`, you can use either HTTP, WS, or IPC values.
      # **Most often, you only need HTTP!**
      uri: https://foo.node.example.com
      # uri: wss://bar.feed.example.com
      # uri: path/to/mainnet/geth.ipc
      
      # For strict HTTP connections, you can configure a http_uri directly.
      http_uri: https://foo.node.example.com

      # You can also configure a websockets URI (used by Silverback SDK).
      ws_uri: wss://bar.feed.example.com
    
      # Specify per-network IPC paths as well.
      ipc_path: path/to/mainnet/geth.ipc
```

## Network Config

There are many ways to configure your networks.
Most of the time, Ape and its L2 plugins configure the best defaults automatically.
Thus, you most likely won't need to modify these configurations.
However, you do need to configure these if you wish to stray from a network's defaults.
The following example shows how to do this.
(note: even though this example uses `ethereum:mainnet`, you can use any of the L2 networks mentioned above, as they all have these config properties).

```yaml
ethereum:
  mainnet:
    # Ethereum mainnet in Ape uses EIP-1559 by default,
    # but we can change that here. Note: most plugins
    # use type 0 by default already, so you don't need
    # to change this if using an `ape-<l2>` plugin.
    default_transaction_type: 0

    # The amount of time to wait for a transaction to be
    # accepted after sending it before raising an error.
    # Most networks use 120 seconds (2 minutes).
    transaction_acceptance_timeout: 60

    # The amount of times to retry fetching a receipt. This is useful
    # because decentralized systems may show the transaction accepted
    # on some nodes but not on others, and potentially RPC requests
    # won't return a receipt immediately after sending its transaction.
    # This config accounts for such delay. The default is `20`.
    max_receipt_retries: 10

    # Set a gas limit here, or use the default of "auto" which
    # estimates gas. Note: local networks tend to use "max" here
    # by default.
    gas_limit: auto

    # Base-fee multipliers are useful for times when the base fee changes
    # before a transaction is sent but after the base fee was derived,
    # thus causing rejection. A multiplier reduces the chance of
    # rejection. The default for live networks is `1.4` times the base fee.
    base_fee_multiplier: 1.2

    # The block time helps Ape make decisions about
    # polling chain data.
    block_time: 10
```

## Running a Network Process

To run a network with a process, use the `ape networks run` command:

```shell
ape networks run
```

By default, `ape networks run` runs a development Node (geth) process.
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
    with networks.ethereum.mainnet.use_provider("node") as provider:
        # We are using a different provider than the one we started with.
        assert start_provider != provider.name
```

Jump between networks to simulate multi-chain behavior.

```python
import click
from ape import networks

@click.command()
def cli():
    with networks.polygon.mainnet.use_provider("node"):
        ...
    with networks.ethereum.mainnet.use_provider("node"):
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
    with networks.fork(provider_name="foundry"):
        ...
        # Do stuff on a local, forked version of mainnet

    # Switch back to mainnet.
```

Learn more about forking networks in the [forked-networks guide](./forking_networks.html).
