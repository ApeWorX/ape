# Ape Console

Ape provides an [IPython](https://ipython.readthedocs.io/) interactive console with useful pre-defined locals to interact with your project.

```bash
ape console --network ethereum:mainnet

In [1]: networks.active_provider.get_block("latest")
Out[1]: Block(gas_data=BlockGasFee(gas_limit=30029267, gas_used=1957793, base_fee=22138196051), consensus_data=BlockConsensus(difficulty=13087655881211628, total_difficulty=43800816864239190379319), hash=HexBytes('0x75af0ab1a0bcd42a6d894574a47d7933dd6d1ad67820245d596bee2464b676cf'), number=14388141, parent_hash=HexBytes('0x75af0ab1a0bcd42a6d894574a47d7933dd6d1ad67820245d596bee2464b676cf'), size=17431, timestamp=1647306023)
```

## Namespace Extras

You can also create scripts to be included in the console namespace by adding a file (`ape_console_extras.py`) to your root project directory.  All non-internal symbols from this file will be included in the console namespace.  Internal symbols are prefixed by an underscore (`_`).

An example file might look something like this:

```python
from eth_utils import encode_hex, decode_hex

_networks = None


def latest(key="number"):
    return getattr(_networks.active_provider.get_block("latest"), key)


def ape_init_extras(networks):
    """Setup _networks so util func can access it"""
    global _networks
    _networks = networks
```

Then both imported util functions and `WETH_ADDRESS` will be available when you launch the console.

```python
In [1]: latest()
Out[1]: 14388241

In [2]: encode_hex(latest('hash'))
Out[2]: '0x68f768988e9bd4be971d527f72483f321975fa52aff9692b6d0e0af71fb77aaf'
```

### Init Function

If you include a function named `ape_init_extras`, it will be executed with the symbols from the existing namespace being provided as keyword arguments.  This allows you to alter the scripts namespace using locals already included in the Ape namespace.  If you return a `dict`, these values will be added to the console namespace.  For example, you could setup an initialized Web3.py object by using one from an existing Ape Provider.

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

You can also add an `ape_console_extras.py` file to the global ape data directory (`$HOME/.ape/ape_console_extras.py`) and it will execute regardless of project context you are in.  This may be useful for variables and utility functions you use across all of your projects.
