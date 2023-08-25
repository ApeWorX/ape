# ape.plugins

```{eval-rst}
.. automodule:: ape.plugins
    :members:
    :show-inheritance:
```

## Base

```{eval-rst}
.. automodule:: ape.plugins.pluggy_patch
    :members:
    :show-inheritance:
```

## Accounts

```{eval-rst}
.. automodule:: ape.plugins.account
    :members:
    :show-inheritance:
```

## Compiler

```{eval-rst}
.. automodule:: ape.plugins.compiler
    :members:
    :show-inheritance:
```

## Config

```{eval-rst}
.. automodule:: ape.plugins.config
    :members:
    :show-inheritance:
```

## Converter

```{eval-rst}
.. automodule:: ape.plugins.converter
    :members:
    :show-inheritance:
```

## Network

```{eval-rst}
.. automodule:: ape.plugins.network
    :members:
    :show-inheritance:
```

## Project

```{eval-rst}
.. automodule:: ape.plugins.project
    :members:
    :show-inheritance:
```

## Query

```{eval-rst}
.. automodule:: ape.plugins.query
    :members:
    :show-inheritance:
```

## Multicall

The `ape_ethereum` core plugin comes with a `multi-call` module.
Yes you're reading this right.
No need to install external modules to do multicall, ape got you covered.
Perform the Multicall call.
This call will trigger again every time the `Call` object is called.

```bash
Raises:
    :class:`~ape_ethereum.multicall.exceptions.UnsupportedChain`: If there is not an instance of Multicall3 deployed on the current chain at the expected address.

Args:
    **call_kwargs: the kwargs to pass through to the call handler.

Returns:
    Iterator[Any]: the sequence of values produced by performing each call stored by this instance.
```

### Usage

Here is an example of how you can use multicall.

```py
from ape_ethereum import multicall

call = multicall.Call()

call.add(contract.myMethod, *call_args)
call.add(contract.myMethod, *call_args)
...  # Add as many calls as desired
call.add(contract.myMethod, *call_args)

a, b, ..., z = call()  # Performs multicall
# OR
# The return type of the multicall is a generator object. So basically this will convert the result returned by the multicall into a list
result = list(call()) 
```

### Practical Example

This is a sample example of how you can perform multicall in a real world scenario. This piece of code will perfrom multicall on a `Uniswap V2` pool contract.

```py
from ape_ethereum import multicall
from ape import project

pool = ["0xF4b8A02D4e8D76070bD7092B54D2cBbe90fa72e9","0x80067013d7F7aF4e86b3890489AcAFe79F31a4Cb"]

for pool_address in pools:
    uniswap_v2_pair_contract = project.IUniswapV2Pair.at(pool_address)
    call.add(uniswap_v2_pair_contract.getReserves)
    multicall_result = list(call())

print(multicall_result[0])

# output
[17368643486106939361172, 31867695075486]
```

<!-- ### Encode Multicall Transaction
Encode the Multicall transaction as a ``TransactionAPI`` object, but do not execute it.
Returns:
```js
:class:`~ape.api.transactions.TransactionAPI`
```

```py
from ape_ethereum import multicall

call = multicall.Call()
call.add(contract.myMethod, *call_args)
call.add(contract.myMethod, *call_args)
...  # Add as many calls as desired
call.add(contract.myMethod, *call_args)

encoded_call = call.as_transaction()
``` -->

## Multicall Transaction

Create a sequence of calls to execute at once using `eth_sendTransaction` via the Multicall3 contract.
Execute the Multicall transaction.
The transaction will broadcast again every time the `Transaction` object is called.

```bash
Raises:
    :class:`UnsupportedChain`: If there is not an instance of Multicall3 deployed
        on the current chain at the expected address.

Args:
    **txn_kwargs: the kwargs to pass through to the transaction handler.

Returns:
    :class:`~ape.api.transactions.ReceiptAPI`
```

### Usage example:

```py
from ape_ethereum import multicall

txn = multitxn.Transaction()
txn.add(contract.myMethod, *call_args)
txn.add(contract.myMethod, *call_args)
...  # Add as many calls as desired to execute
txn.add(contract.myMethod, *call_args)
a, b, ..., z = txn(sender=my_signer)  # Sends the multical transaction
# OR
result = list(txn(sender=my_signer))
```
