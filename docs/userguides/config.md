# Configure Ape

A `ape-config.yaml` file allows you to configure ape. This guide serves as an index of the settings you can include 
in an `ape-config.yaml` file.

## Deployments

Share deployments with teammates.

```yaml
deployments:
  ethereum:
    mainnet:
      MyContract:
      - 0xc123aAacCcbBbaAa444777000111222111222111
    ropsten:
      MyContract:
      - 0xc222000cCcbBbaAa444777000111222111222222
```

## Networks

Set default networks.

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
