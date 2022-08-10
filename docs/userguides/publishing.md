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

If your project contains delpoyments that you wish to include in its package manifest, use the [track_deployment()](../methoddocs/managers.html#ape.managers.project.manager.ProjectManager.track_deployment) method.
Example:

```python
from ape import accounts, project

account = accounts.load("mainnet-account")

# Assume your project has a contract named 'MyContract' with constructor that accepts argument '123'.
contract = project.MyContract.deploy(123, sender=account)
project.track_deployment(contract)
```

**NOTE**: If the contract is already deployed, you can use the [.at()](../methoddocs/contracts.html#ape.contracts.base.ContractContainer.at) method on the contract container to get an instance first.
For more information on accessing contract instances, follow [this guide](./contracts.html).
