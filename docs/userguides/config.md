# Configure Ape

An `ape-config.yaml` file allows you to configure ape. This guide serves as an index of the settings you can include 
in an `ape-config.yaml` file.

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

## Networks

Set default network and network providers:

```yaml
ethereum:
  default_network: mainnet-fork
  mainnet-fork:
    default_provider: hardhat
```

## Plugins

Set which plugins you want to always use:

```yaml
plugins:
  - name: solidity
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
