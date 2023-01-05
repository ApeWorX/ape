# Plugins

Plugins are core to Ape's architecture.
Here are some plugin examples in Ape:

- `CompilerAPI`: For supporting various languages, like Vyper or Solidity.
- `ProviderAPI`: For connecting the blockchain, such as Alchemy, Geth, or a local Hardhat node.
- `EcosystemAPI`: A suite of networks, such as Ethereum, Fantom, or Starknet.
- CLI plugins: Extending the `click` CLI in Ape.

## Core Plugins

Ape ships with core plugins to help Ape work out-of-the-box.
To see the core plugins that come with Ape, run the following command:

```bash
ape plugins list --all
```

Normally, the `ape plugins list` command shows you all the plugins you have installed.
However, when you include the `--all` flag, it shows the core plugins and the available plugins as well.
**NOTE**: The available plugins list is trusted and from the ApeWorX organization, however you can install third-party plugins from other sources as well.

## Installing Plugins

To add plugins to your project, edit your `ape-config.yaml` file:

```yaml
plugins:
  - name: solidity
    version: 0.4.0
  - name: hardhat
  - name: ens
  - name: etherscan
```

The `name` field is required.
Additionally, you may specify a `version`.

To install the plugins listed in your project, run the following command from the project's root directory:

```bash
ape plugins install .
```

To install plugins individually, run the following command:

```bash
ape plugins install vyper solidity
```

## Plugin Types

There are many types of plugins available, including compilers, providers, networks, and CLI-based plugins.
To learn more about the different types of plugins, see the [Developing a Plugin Guide](./developing_plugins.html).
