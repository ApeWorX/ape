# Contracts

You can interact with contracts pythonically using ape!
First, we need to obtain a contract instance.
One way to do this is to deploy a contract.
The other way is to initialize an already-deployed contract using its address.

## From Deploy

Deploy contracts from your project using the `project` root-level object.
The names of your contracts are properties on the `project` object (e.g. `project.MyContract`) and their types are [ContractContainer](../methoddocs/contracts.html#ape.contracts.base.ContractContainer).

**NOTE**: To avoid naming collisions with other properties on the `project` object, you can also use the [get_contract()](../methoddocs/managers.html#ape.managers.project.manager.ProjectManager.get_contract) method to retrieve contract containers.

When you deploy contracts, you get back a `ContractInstance`:

```python
from ape import accounts, project

dev = accounts.load("dev")
contract = project.MyContract.deploy(sender=dev)
```

## From Project Contract Address

You can also use the [at() method](../methoddocs/contracts.html#ape.contracts.base.ContractContainer.at) from the same top-level project manager when you know the address of an already-deployed contract:

```python
from ape import project

contract = project.MyContract.at("0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45")
```

## From Any Address

If you already know the address of a contract, you can create instances of it using the `Contract` top-level factory:

```python
from ape import Contract

contract = Contract("0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45")
```

It will fetch the `contract-type` using the explorer plugin from the active network, such as [ape-etherscan](https://github.com/ApeWorX/ape-etherscan).

If you have the [ENS plugin](https://github.com/ApeWorX/ape-ens) installed, you can use `.eth` domain names as the argument:

```python
from ape import Contract

contract = Contract("v2.registry.ychad.eth")
```

## From Previous Deployment

Ape keeps track of your deployments for you so you can always refer back to a version that you deployed previously.
On live networks, this history of deployments is saved; on local networks, this history lasts for the duration of your script.

Let's say you previously deployed a smart contract called `MyContract` on the rinkeby test network.
You could then refer back to it like so:

```python
from ape import project, chain, accounts

def main():
  account = accounts.test_accounts[0]
  my_contract = chain.contracts.get_deployments(project.MyContract)[-1]
```

or

```python
from ape import project, accounts

def main():
  account = accounts.test_accounts[0]
  my_contract = project.MyContract.deployments[-1]
```

`my_contract` will be of type `ContractInstance`.
`get_deployments` returns a list of deployments you made of that contract type.

## Contract Interaction

Then, after you have a contract instance, you can call methods on the contract.
For example, let's say you have a Vyper contract containing some functions:

```python
@pure
@external
def get_static_list() -> DynArray[uint256, 3]:
    return [1, 2, 3]

@external
def set_number(num: uint256):
    assert msg.sender == self.owner, "!authorized"
    self.prevNumber = self.myNumber
    self.myNumber = num
```

You can call those functions by doing:

```python
assert contract.get_static_list() == [1, 2, 3]

# Mutable calls are transactions and require a sender
receipt = contract.set_number(sender=dev)
```
