# Configure Ape

An `ape-config.yaml` file allows you to configure ape. This guide serves as an index of the settings you can include 
in an `ape-config.yaml` file.

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

Set default networks:

```yaml
ethereum:
  development:
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
