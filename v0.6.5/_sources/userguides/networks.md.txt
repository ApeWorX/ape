# Networks

When interacting with the blockchain, you will have to select a network.

## Selecting a Network

Commonly, you will use the `--network` option to configure your network during Ape commands.
The following is a list of common Ape commands that can use the `--network` option:

```bash
ape test --network ethereum:local:foundry
ape console --network arbitrum:testnet:alchemy
```

You can also use the `--network` option on scripts that use the `main()` method approach or scripts that implement that `NetworkBoundCommand` command type.
See [the scripting guide](./scripts.html) to learn more about scripts and how to add the network option.

**NOTE**: You can omit values to use defaults.
For example, the default ecosystem is `ethereum` and the default network is `local`, so you can do:

```bash
ape run --network ::foundry
```

as a short-cut for `ethereum:local:foundry`.

## Configuring Networks

Change network defaults using your project's `ape-config.yaml` file.
The following configuration changes the default ecosystem, network, and provider such that if you omitted the `--network` option on network-bound commands, it would use the value `<ecosystem-name>:<network-name>:<provider-name>`.

```yaml
default_ecosystem: <ecosystem-name>

<ecosystem-name>:
  default_network: <network-name>
  <network-name>:
    default_provider: <provider-name>
```

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

For the local network configuration, the default is `"max"`. Otherwise it is `"auto"`.

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

## Ad-hoc Network Connection

If you would like to connect to a URI using the `geth` provider, you can specify a URI for the provider name in the `--network` option:

```bash
ape run script --network etheruem:mainnet:https://foo.bar
```

Additionally, if you want to connect to an unknown ecosystem or network, you can use the URI by itself.
However, this is not recommended.

```bash
ape run script --network https://foo.bar
```

**WARNING**: The recommended approach is to find or build a plugin to have more native support.
Some reasons for this include:

1. You may need to integrate with other plugins, such as explorer plugins for getting contract types.
2. Some chains may not implement EIP-1559 or may have forked from a specific configuration.
3. Response differences in uncommon blocks, such as the `"pending"` block or the genesis block.
4. Revert messages and exception-handling differences.
5. You are limited to using `web3.py` and EVM-based chains.
