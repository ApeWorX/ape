# Publishing

Publishing smart-contract packages using Ape is influenced from [EIP-2678](https://eips.ethereum.org/EIPS/eip-2678) and uses the [ethpm-types](https://github.com/ApeWorX/ethpm-types) Python package extensively (which is also managed by the ApeWorX organization).
This guide exists to walk through the steps of publishing your project.

## Compilation

First, your project must compile.

```bash
ape compile
```

To learn more about project compilation, follow [this guide](./compile.html).
Once your project has successfully compiled, you will have the start of your `PackageManifest` generated in your project's `.build/` directory.

## Tracking Deployments

If your project contains deployments that you wish to include in its package manifest, use the [project.deployments.track](../methoddocs/managers.html#ape.managers.project.manager.DeploymentManager.track) method.
Example:

```python
from ape import accounts, project

account = accounts.load("mainnet-account")

# Assume your project has a contract named 'MyContract' with constructor that accepts argument '123'.
contract = project.MyContract.deploy(123, sender=account)
project.deployments.track(contract)
```

If the contract is already deployed, you can use [Contract](../methoddocs/ape.html#ape.Contract) to get a contract instance:

```python
from ape import Contract, project

contract = Contract("0x12c17f958d2ee523a2206206994597c13d831e34")
project.deployments.track(contract)
```

For more information on accessing contract instances, follow [this guide](./contracts.html).

## Publishing to Explorer

If you want to publish your contracts to an explorer, you can use the [publish_contract](../methoddocs/api.html#ape.explorers.ExplorerAPI.publish_contract) on the `ExplorerAPI`.

```python
from ape import networks

networks.provider.network.explorer.publish_contract("0x123...")
```

If you want to automatically publish the source code upon deployment, you can use the `publish=` kwarg on the `deploy` methods:

```python
from ape import accounts, project

account = accounts.load("<ALIAS>")
account.deploy(project.MyContract, publish=True)
```
