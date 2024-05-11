# Configure Ape

You can configure Ape using configuration files with the name `ape-config.yaml`.
There are two locations you can place an `ape-config.yaml` file.

1. In the root of your project
2. In your `$HOME/.ape` directory (global)

Project settings take precedent, but global settings allow you to configure preferences across all projects, such as your default mainnet provider (e.g. Alchemy versus running your own node).

This guide serves as an index of the settings you can include in any `ape-config.yaml` file.
This guide is **PURPOSELY** alphabetized to facilitate easier look-up of keys.

Most of the features in this guide are documented more-fully elsewhere in the user-guides.

However, here is a list of common-use cases requiring the `ape-config.yaml` file to help you:

1. Setting up a custom node RPC: See the [geth](#geth) section.
2. Setting up project dependencies: See the [dependencies](#dependencies) section.
3. Declaring your project's plugins: See the [plugins](#plugins) section.

## Contracts Folder

Specify a different path to your `contracts/` directory.
This is useful when using a different naming convention, such as `src/` rather than `contracts/`.

```yaml
contracts_folder: src
```

You can also use an absolute path.
This is useful for projects that compile contracts outside their directory.

```yaml
contracts_folder: "~/GlobalContracts"
```

## Default Ecosystem

You can change the default ecosystem by including the following:

```yaml
default_ecosystem: fantom
```

The default ecosystem is `ethereum`.

## Dependencies

Configure dependencies for your ape project.
To learn more about dependencies, see [this guide](./dependencies.html).

A simple example of configuring dependencies looks like this:

```yaml
dependencies:
  - name: OpenZeppelin
    github: OpenZeppelin/openzeppelin-contracts
    version: 4.4.2
```

## Deployments

Set deployments that were made outside of Ape in your `ape-config.yaml` to create past-deployment-based contract instances in Ape:
(See [this example](./contracts.html#from-previous-deployment) for more information on this feature).

Config example:

```yaml
deployments:
  ethereum:
    mainnet:
      - contract_type: MyContract
        address: 0x5FbDB2315678afecb367f032d93F642f64180aa3
    goerli:
      - contract_type: MyContract
        address: 0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
```

When connected to Ethereum mainnet, reference the deployment by doing:

```python
from ape import project

contract = project.MyContract.deployments[0]
```

**NOTE**: Ape does not add or edit deployments in your `ape-config.yaml` file.

## Geth

When using the `geth` provider, you can customize its settings.
For example, to change the URI for an Ethereum network, do:

```yaml
geth:
  ethereum:
    mainnet:
      uri: http://localhost:5030
```

Now, the `ape-geth` core plugin will use the URL `http://localhost:5030` to connect and make requests.

**WARN**: Instead of using `ape-geth` to connect to an Infura or Alchemy node, use the [ape-infura](https://github.com/ApeWorX/ape-infura) or [ape-alchemy](https://github.com/ApeWorX/ape-alchemy) provider plugins instead, which have their own way of managing API keys via environment variables.

For more information on networking as a whole, see [this guide](./networks.html).

## Networks

Set default network and network providers:

```yaml
ethereum:
  default_network: mainnet-fork
  mainnet_fork:
    default_provider: hardhat
```

Set the gas limit for a given network:

```yaml
ethereum:
  default_network: mainnet-fork
  mainnet_fork:
    gas_limit: max
```

You may use one of:

- `"auto"` - gas limit is estimated for each transaction
- `"max"` - the maximum block gas limit is used
- A number or numeric string, base 10 or 16 (e.g. `1234`, `"1234"`, `0x1234`, `"0x1234"`)
- An object with key `"auto"` for specifying an estimate-multiplier for transaction insurance

To use the auto-multiplier, make your config like this:

```yaml
ethereum:
  mainnet:
    gas_limit:
      auto:
        multiplier: 1.2  # Multiply 1.2 times the result of eth_estimateGas
```

For the local network configuration, the default is `"max"`. Otherwise, it is `"auto"`.

## Plugins

Set which `ape` plugins you want to always use.

**NOTE**: The `ape-` prefix is not needed and shouldn't be included here.

```yaml
plugins:
  - name: solidity # ape-solidity plugin
    version: 0.1.0b2
  - name: ens
```

Install these plugins by running command:

```bash
ape plugins install .
```

## Testing

Configure your test accounts:

```yaml
test:
  mnemonic: test test test test test test test test test test test junk
  number_of_accounts: 5
```
