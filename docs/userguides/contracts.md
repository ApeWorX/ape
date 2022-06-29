# Contracts

You can interact with contracts pythonically using ape!
First, we need to obtain a contract instance.
One way to do this is to deploy a contract.
The other way is to initialize an already-deployed contract using its address.

## From Deploy

When you deploy contracts, you get back a `ContractInstance`:

```python
from ape import accounts, project

dev = accounts.load("dev")
contract = project.MyContract.deploy(sender=dev)
```

## From Contract

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
