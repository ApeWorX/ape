# Ape Console

Ape provides an IPython interactive console with useful pre-defined locals to interact with your project.

```bash
ape console --network ethereum:mainnet

In [1]: weth = Contract(address='0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2', contract_type=project.contracts['ERC20'])

In [2]: weth.totalSupply()
Out[2]: 7065522116676615294347037
```

## Namespace Extras

You can also create scripts to be included in the console namespace by adding a file (`ape_console_extras.py`) to your root project directory.  All non-internal symbols from this file will be included in the console namespace.  Internal symbols are prefixed by an underscore (`_`).

An example file might look something like this:

```python
from eth_utils import encode_hex, decode_hex

WETH_ADDRESS = "0xc02aaa39b223fe8d0a0e5c4f27ead9083c756cc2"
```

Then both imported util functions and `WETH_ADDRESS` will be available when you launch the console.

```python
In [1]: decode_hex(WETH_ADDRESS)
Out[1]: b"\xc0*\xaa9\xb2#\xfe\x8d\n\x0e\\O'\xea\xd9\x08<ul\xc2"
```

### Init Function

If you include a function named `init_extras`, it will be executed with the symbols from the existing namespace being provided as keyword arguments.  This allows you to alter the scripts namespace using locals already included in the Ape namespace.  If you return a `dict`, these values will be added to the console namespace.  For example, you could setup an initialized Web3.py object by using one from an existing Ape Provider.

```python
def init_extras(chain):
    return {"web3": chain.provider._web3}
```

Then `web3` will be available to use immediately.

```python
In [1]: web3.eth.chain_id
Out[1]: 1
```

### Global Extras

You can also add an `ape_console_extras.py` file to the global ape data directory (`$HOME/.ape/ape_console_extras.py`) and it will execute regardless of project context you are in.  This may be useful for variables and utility functions you use across all of your projects.
