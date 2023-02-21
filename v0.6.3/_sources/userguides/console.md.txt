# Ape Console

Ape provides an [IPython](https://ipython.readthedocs.io/) interactive console with useful pre-defined locals to interact with your project.

```bash
ape console --network ethereum:mainnet

In [1]: chain.blocks.head.timestamp
Out[1]: 1647323479
```

WARNING: Contract changes are not reflected in the active console session.
If you need to make changes to your contract, you must re-start your console session for the compiler to handle the changes.

## Ape Namespace

Your console comes with pre-initialized root ape objects in your namespace.

|    Name    |                                                   Class                                                    |
| :--------: | :--------------------------------------------------------------------------------------------------------: |
| `accounts` |       [AccountManager](../methoddocs/managers.html?highlight=accounts#module-ape.managers.accounts)        |
| `networks` |       [NetworkManager](../methoddocs/managers.html?highlight=networks#module-ape.managers.networks)        |
|  `chain`   |           [ChainManager](../methoddocs/managers.html?highlight=chain#module-ape.managers.chain)            |
| `project`  |    [ProjectManager](../methoddocs/managers.html?highlight=project#module-ape.managers.project.manager)     |
|  `query`   |           [QueryManager](../methoddocs/managers.html?highlight=query#module-ape.managers.query)            |
| `convert`  | [convert](../methoddocs/managers.html?highlight=query#ape.managers.converters.AddressAPIConverter.convert) |
|   `ape`    |                                       [ape](../methoddocs/ape.html)                                        |

You can access them as if they are already initialized:

First, launch the console:

```bash
ape console
```

Then, type the name of the item and you will see its Python representation:

```python
In [1]: networks
Out[1]: <NetworkManager active_provider=<test chain_id=61>>
```

**NOTE**: To change the network of the active console, use the `--network` option.
Follow [this guide](./networks.html) for more information on networks in Ape.

## Namespace Extras

You can also create scripts to be included in the console namespace by adding a file (`ape_console_extras.py`) to your root project directory.  All non-internal symbols from this file will be included in the console namespace.  Internal symbols are prefixed by an underscore (`_`).

An example file might look something like this:

```python
from eth_utils import encode_hex, decode_hex


def latest(key):
    return getattr(networks.active_provider.get_block("latest"), key)
```

Then both imported util functions and `WETH_ADDRESS` will be available when you launch the console.

```python
In [1]: latest('number')
Out[1]: 14388241

In [2]: encode_hex(latest('hash'))
Out[2]: '0x68f768988e9bd4be971d527f72483f321975fa52aff9692b6d0e0af71fb77aaf'
```

### Init Function

If you include a function named `ape_init_extras`, it will be executed with the symbols from the existing namespace being provided as keyword arguments.  This allows you to alter the scripts namespace using locals already included in the Ape namespace.  If you return a `dict`, these values will be added to the console namespace.  For example, you could set up an initialized Web3.py object by using one from an existing Ape Provider.

```python
def ape_init_extras(chain):
    return {"web3": chain.provider._web3}
```

Then `web3` will be available to use immediately.

```python
In [1]: web3.eth.chain_id
Out[1]: 1
```

### Global Extras

You can also add an `ape_console_extras.py` file to the global ape data directory (`$HOME/.ape/ape_console_extras.py`) and it will execute regardless of what project context you are in.  This may be useful for variables and utility functions you use across all of your projects.
