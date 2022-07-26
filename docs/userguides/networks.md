# Network

When interacting with the blockchain, you will have to select a network.

## Selecting a Network

Commonly, you will use the `--network` option to configre your network during Ape commands.
The following is a list of common Ape commands that can use the `--network` option:

```bash
ape test --network ethereum:local:foundry
ape run deploy --network ethereum:mainnet:geth  # NOTE: Must be defined if using CLI script
ape console --network arbitrum:testnet:alchemy
```

**NOTE**: You can omit values to use defaults.
For example, the default ecosystem is `ethereum` and the default network is `local`, so you can do:

```bash
ape run --network ::foundry
```

as a short-cut for `ethereum:local:foundry`.

# Local Network

The default network in Ape is the local network (keyword `"local"`).
It is meant for running tests and debugging contracts.
Out-of-the-box, Ape ships with two development providers you can use for the `local` network:

* [EthTester](https://github.com/ethereum/eth-tester)
* An Ephemeral Geth process

```bash
ape test --network ::test
ape test --network ::geth  # Launch a local Development geth process
```

To learn more about testing in ape, follow [this guide]("../testing.html).

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

**The recommended approach is to find or build a plugin to have more native support.**
