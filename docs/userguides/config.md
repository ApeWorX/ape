# Configure Ape

You can configure Ape using a `pyproject.toml` file and the prefix `tool.ape` or any configuration file named `ape-config.[yaml|yml|json]`.
There are two locations you can place config files.

1. In the root of your project
2. In your `$HOME/.ape` directory (global)

Project settings take precedent, but global settings allow you to configure preferences across all projects, such as your default mainnet provider (e.g. Alchemy versus running your own node).

This guide serves as an index of some settings you can include in any `ape-config.yaml` file.
This guide is **PURPOSELY** alphabetized to facilitate easier look-up of keys.
Plugins for Ape may define their own configs.

Most of the features in this guide are documented more-fully elsewhere in the user-guides.

However, here is a list of common-use cases requiring the `ape-config.yaml` file to help you:

1. Setting up a custom node RPC: See the [node](#node) section.
2. Setting up project dependencies: See the [dependencies](#dependencies) section.
3. Declaring your project's plugins: See the [plugins](#plugins) section.

**Environment Variables**: `ape-config.yaml` files support environment-variable expansion.
Simply include environment variables (with the `$` prefix) in your config file and Ape will automatically expand them.

```toml
[tool.ape.plugin]
secret_rpc = "$MY_SECRET_RPC"
```

Or the equivalent YAML:

```yaml
plugin:
  secret_rpc: $MY_SECRET_RPC
```

This helps keep your secrets out of Ape!

## Base Path

Change the base path if it is different than your project root.
For example, imagine a project structure like:

```
project
└── src/
    └── contracts/
        └── MyContract.sol
```

In this case, you want to configure Ape like:

```toml
[tool.ape]
base_path = "src"
```

Or the equivalent YAML:

```yaml
base_path: src
```

This way, `MyContract.vy`'s source ID will be `"contracts/Factory.vy"` and not `"src/contracts/Factory.vy"`.
Some dependencies, such as python-based ones like `snekmate`, use this structure.

## Contracts Folder

Specify a different path to your `contracts/` directory.
This is useful when using a different naming convention, such as `src/` rather than `contracts/`.

```toml
[tool.ape]
contracts_folder = "src"
```

Or the equivalent YAML:

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

```toml
[tool.ape]
default_ecosystem = "fantom"
```

Or the equivalent YAML:

```yaml
default_ecosystem: fantom
```

The default ecosystem is `ethereum`.

## Dependencies

Configure dependencies for your ape project.
To learn more about dependencies, see [this guide](./dependencies.html).

A simple example of configuring dependencies looks like this:

```toml
[[tool.ape.dependencies]]
name = "openzeppelin"
github = "OpenZeppelin/openzeppelin-contracts"
version = "4.4.2"
```

Or the equivalent YAML:

```yaml
dependencies:
  - name: openzeppelin
    github: OpenZeppelin/openzeppelin-contracts
    version: 4.4.2
```

## Deployments

Set deployments that were made outside of Ape in your `ape-config.yaml` to create past-deployment-based contract instances in Ape:
(See [this example](./contracts.html#from-previous-deployment) for more information on this feature).

Config example:

```toml
[[tool.ape.deployments.ethereum.mainnet]]
contract_type = "MyContract"
address = "0x5FbDB2315678afecb367f032d93F642f64180aa3"

[[tool.ape.deployments.ethereum.sepolia]]
contract_type = "MyContract"
address = "0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512"
```

Or the equivalent YAML:

```yaml
deployments:
  ethereum:
    mainnet:
      - contract_type: MyContract
        address: 0x5FbDB2315678afecb367f032d93F642f64180aa3
    sepolia:
      - contract_type: MyContract
        address: 0xe7f1725E7734CE288F8367e1Bb143E90bb3F0512
```

When connected to Ethereum mainnet, reference the deployment by doing:

```python
from ape import project

contract = project.MyContract.deployments[0]
```

```{note}
Ape does not add or edit deployments in your `ape-config.yaml` file.
```

## Node

When using the `node` provider, you can customize its settings.
For example, to change the URI for an Ethereum network, do:

```toml
[tool.ape.node.ethereum.mainnet]
uri = "http://localhost:5030"
```

Or the equivalent YAML:

```yaml
node:
  ethereum:
    mainnet:
      uri: http://localhost:5030
```

Now, the `ape-node` core plugin will use the URL `http://localhost:5030` to connect and make requests.

```{warning}
Instead of using `ape-node` to connect to an Infura or Alchemy node, use the [ape-infura](https://github.com/ApeWorX/ape-infura) or [ape-alchemy](https://github.com/ApeWorX/ape-alchemy) provider plugins instead, which have their own way of managing API keys via environment variables.
```

For more information on networking as a whole, see [this guide](./networks.html).

## Networks

Set default network and network providers:

```toml
[tool.ape.ethereum]
default_network = "mainnet-fork"

[tool.ape.ethereum.mainnet_fork]
default_provider = "hardhat"
```

Or the equivalent YAML:

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

```{note}
The `ape-` prefix is not needed and shouldn't be included here.
```

```toml
[[tool.ape.plugins]]
name = "solidity"
version = "0.1.0b2"

[[tool.ape.plugins]]
name = "ens"
```

Or the equivalent YAML:

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

## Request Headers

For Ape's HTTP usage, such as requests made via `web3.py`, optionally specify extra request headers.

```yaml
request_headers:
  # NOTE: Only using Content-Type as an example; can be any header key/value.
  Content-Type: application/json
```

You can also specify request headers at the ecosystem, network, and provider levels:

```yaml
# NOTE: All the headers are the same only for demo purposes.
# You can use headers you want for any of these config locations.
ethereum:
  # Apply to all requests made to ethereum networks.
  request_headers:
    Content-Type: application/json
  
  mainnet:
    # Apply to all requests made to ethereum:mainnet (using any provider)
    request_headers:
      Content-Type: application/json
  
node:
  # Apply to any request using the `node` provider.
  request_headers:
    Content-Type: application/json
```

To learn more about how request headers work in Ape, see [this section of the Networking guide](./networks.html#request-headers).

## Testing

Configure your test accounts:

```yaml
test:
  mnemonic: test test test test test test test test test test test junk
  number_of_accounts: 5
```

## Plugin Settings

To configure a plugin, use the name of the plugin followed by any of the plugin's settings.
For example, to configure the `ape-solidity` plugin, you would do:

```yaml
solidity:
  evm_version: paris  # Or any other setting defined in `ape-solidity`.
```

## Non-plugin settings

Projects can use their own settings.
Meaning, you can put whatever data you want in an `ape-config.yaml` file and read it in Ape.

```{note}
These types of settings lack sophisticated Pydantic validation and are limited in that respect.
Simple validation, however, will occur, such as if it the value `isnumeric()`, it will be converted to an int, or if the value is a boolean name it will convert it to a `bool`.
```

```yaml
my_project_key:
  my_string: "my_value"
  my_int: 123
  my_bool: True
```

Then, to access it (or any setting for that matter):

```python
from ape import project

my_str = project.config.my_project_key.my_string  #  "my_value"
my_int = project.config.my_project_key.my_int  #  123
my_bool = project.config.my_project_key.my_bool  #  True
```
