# Configure Ape

You can configure Ape using configuration files with the name `ape-config.yaml`.
There are two locations you can place an `ape-config.yaml` file.

1. In the root of your project
2. In your `$HOME/.ape` directory (global)

Project settings take precedent, but global settings allow you to configure preferences across all projects, such as your default mainnet provider (e.g. Alchemy versus running your own node).

This guide serves as an index of the settings you can include in any `ape-config.yaml` file.

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

Share import deployments to public networks with your teammates:

```yaml
deployments:
  ethereum:
    mainnet:
      - contract_type: MyContract
        address: 0xc123aAacCcbBbaAa444777000111222111222111
    ropsten:
      - contract_type: MyContract
        address: 0xc222000cCcbBbaAa444777000111222111222222
```

## Geth

When using the `geth` provider, you can customize its settings.
For example, to change the URI for an Ethereum network, do:

```yaml
geth:
  ethereum:
    mainnet:
      uri: http://localhost:5030
```

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

For the local network configuration, the default is `"max"`. Otherwise it is `"auto"`.

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
ape plugins install
```

## Testing

Configure your test accounts:

```yaml
test:
  mnemonic: test test test test test test test test test test test junk
  number_of_accounts: 5
```
