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

You can alternatively use this syntax instead:

```python
from ape import accounts, project

dev = accounts.load("dev")
contract = dev.deploy(project.MyContract)
```

If your contract requires constructor arguments then you will need to pass them to the contract in the [args](./transactions.html) when deploying like this:

```python
from ape import accounts, project

dev = accounts.load("dev")
contract = project.MyContract.deploy("argument1", "argument2", sender=dev)
```

you can alternatively use this syntax instead:

```python
from ape import accounts, project

dev = accounts.load("dev")
contract = accounts.dev.deploy(project.MyContract, "argument1", "argument2")
```

With this technique, you can feed as many constructor arguments as your contract constructor requires.

**NOTE**: You can also publish the contract source code to an explorer upon deployment using the `publish=` kwarg on the deploy methods.
More information on publishing contracts can be found in [this guide](./publishing.html).

If you do not pass the correct amount of constructor arguments when deploying, you will get an error showing your arguments don't match what is in the ABI:

```bash
ArgumentsLengthError: The number of the given arguments (0) do not match what is defined in the ABI (2).
```

In this case it is saying that you have fed 0 constructor arguments but the contract requires 2 constructor arguments to deploy.

To show the arguments that your constructor requires you can use the .constructor method to see the constructor arguments that your contract requires:

```python
In [0]: project.MyContract.constructor
Out[0]: constructor(string argument1, string argument2)
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

## From ABIs

You can load contracts using their ABIs:

```python
from ape import Contract

address = "0x68b3465833fb72A70ecDF485E0e4C7bD8665Fc45"

# Using a JSON str:
contract = Contract(
    address, abi='[{"name":"foo","type":"fallback", "stateMutability":"nonpayable"}]'
)

# Using a JSON file path:
contract = Contract(address, abi="abi.json")

# Using a Python dictionary from JSON:
contract = Contract(
    address,
    abi=[{"name":"foo","type":"fallback", "stateMutability":"nonpayable"}]
)
```

This will create the Contract instance from the given ABI.

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

### Default, Fallback, and Direct Calls

To directly call an address, such as invoking a contract's `fallback` or `receive` method, call a contract instance directly:

```python
from ape import Contract, accounts

sender = accounts.load("dev")
contract = Contract("0x123...")

# Call the contract's fallback method.
receipt = contract(sender=sender, gas=40000, data="0x123")
```

### Private Transactions

If you are using a provider that allows private mempool transactions, you are able to use the `private=True` kwarg to publish your transaction into a private mempool.
For example, EVM providers likely will use the `eth_sendPrivateTransaction` RPC to achieve this.

To send a private transaction, do the following:

```python
receipt = contract.set_number(sender=dev, private=True)
```

The `private=True` is available on all contract interactions.

## Decoding and Encoding Inputs

If you want to separately decode and encode inputs without sending a transaction or making a call, you can achieve this with Ape.
If you know the method you want to use when decoding or encoding, you can call methods `encode_input()` or `decode_input()` on the method handler from a contract:

```python
from ape import Contract

# HexBytes(0x3fb5c1cb00000000000000000000000000000000000000000000000000000000000000de)
contract = Contract("0x...")
bytes_value = contract.my_method.encode_input(0, 1, 2)
```

In the example above, the bytes value returned contains the method ID selector prefix `3fb5c1c`.
Alternatively, you can decode input:

```python
from eth_pydantic_types import HexBytes
from ape import Contract

contract = Contract("0x...")
selector_str, input_dict = contract.my_method.decode_input(HexBytes("0x123..."))
```

In the example above, `selector_str` is the string version of the method ID, e.g. `my_method(unit256,uint256)`.
The input dict is a mapping of input names to their decoded values, e.g `{"foo": 2, "owner": "0x123..."}`.
If an input does not have a name, its key is its stringified input index.

If you don't know the method's ABI and you have calldata, you can use a `ContractInstance` or `ContractContainer` directly:

```python
import ape

# Fetch a contract
contract = ape.Contract("0x...")

# Alternative, use a contract container from ape.project
# contract = ape.project.MyContract

# Only works if unique amount of args.
bytes_value = contract.encode_input(0, 1, 2, 4, 5)
method_id, input_dict = contract.decode_input(bytes_value)
```

## Multi-Call and Multi-Transaction

The `ape_ethereum` core plugin comes with a `multicall` module containing tools for interacting with the [multicall3 smart contract](https://github.com/mds1/multicall).
Multicall allows you to group function calls and transactions into a single call or transaction.

Here is an example of how you can use the multicall module:

```python
import ape
from ape_ethereum import multicall


ADDRESSES = ("0xF4b8A02D4e8D76070bD7092B54D2cBbe90fa72e9", "0x80067013d7F7aF4e86b3890489AcAFe79F31a4Cb")
POOLS = [ape.project.IPool.at(a) for a in ADDRESSES]


def main():
    # Use multi-call.
    call = multicall.Call()
    for pool in POOLS:
        call.add(pool.getReserves)
    
    print(list(call()))
    
    # Use multi-transaction.
    tx = multicall.Transaction()
    for pool in POOLS:
        tx.add(pool.ApplyDiscount, 123)
    
    acct = ape.accounts.load("signer")
    for result in tx(sender=acct):
        print(result)
```
