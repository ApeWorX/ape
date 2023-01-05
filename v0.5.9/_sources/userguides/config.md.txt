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

## Default Ecosystem

You can change the default ecosystem by including the following:

```yaml
default_ecosystem: fantom
```

The default ecosystem is `ethereum`.

## Dependencies

Configure dependencies for your ape project.
Ape downloads and caches dependencies in the `.ape/packages/<name>/<version-id>` directory where `<name>` refers to the name of the dependency and `<version-id>` refers to the version or branch of the package.

For example:

```yaml
dependencies:
  - name: OpenZeppelin
    github: OpenZeppelin/openzeppelin-contracts
    version: 4.4.2
```

will download the [Open Zeppelin](https://github.com/OpenZeppelin/openzeppelin-contracts) package with version `4.4.2`.

To ignore files from a dependency project, use the `exclude` setting to specify glob patterns:

```yaml
dependencies:
  - name: dependency-project-name
    github: org-name/dependency-project-name
    exclude:
      - package.json    # Ignore package.json files.
      - mocks/**/*      # Ignore all files in the 'mocks' directory
```

To use dependencies in the `ape-solidity` plugin, configure `import_remappings`:

```yaml
solidity: 
  import_remapping:
    - "@openzeppelin=OpenZeppelin/4.4.2"
```

Now, in your solidity files, import `OpenZeppelin` sources via:

```solidity
import "@openzeppelin/token/ERC721/ERC721.sol";
```

You can also set the branch and name of the dependency's contracts folder, e.g.:

```yaml
dependencies:
  - name: DappToolsERC20
    github: dapphub/erc20
    branch: dappnix
    contracts_folder: src
```

You can also use local dependencies:

```yaml
dependencies:
  - name: MyDependency
    local: local/path/to/MyDependency
    contracts_folder: src/contracts
```

This is helpful when:

- Working on multiple packages at once
- When there is not a suitable `DependencyAPI` implementation available for downloading your dependency

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
  gas_limit: max
```

You may use one of:

- `"auto"` - gas limit is estimated for each transaction
- `"max"` - the maximum block gas limit is used
- A number or numeric string, base 10 or 16 (e.g. `1234`, `"1234"`, `0x1234`, `"0x1234"`)

For the local network configuration, the default is `"max"`. Otherwise it is `"auto"`.

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
