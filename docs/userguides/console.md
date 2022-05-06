# Ape Console

Ape provides an [IPython](https://ipython.readthedocs.io/) interactive console with useful pre-defined locals to interact with your project.

```bash
ape console --network ethereum:mainnet

In [1]: chain.blocks.head.timestamp
Out[1]: 1647323479
```

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

### Console Variables

* **accounts**

provides access to account manager for loading, creating, and interfacing with accounts

```bash
$ ape accounts generate demo_account
Add extra entropy for key generation...: 
Create Passphrase: 
Repeat for confirmation: 
SUCCESS: A new account '0xB1b1A92A6f7435ba375e4cc470aED1e951e92fe5' has been added with the id 'demo_account'
$ ape console

In [1]: accounts.load("demo_account")
Out[1]: <KeyfileAccount address=0xB1b1A92A6f7435ba375e4cc470aED1e951e92fe5 alias=demo_account>
IN [2]: exit

$ ape accounts delete demo_account
Enter passphrase to delete 'demo_account' []: 
SUCCESS: Account 'demo_account' has been deleted

```


* **chain**

Chain provides access to the current connected blockchain. If you connect to a local local provider, you have full control of the entire chain. Which includes: mining, querying, and other features.

```bash
$ ape console
In [1]: chain.chain_id
Out[1]: 61

In [2]: chain.blocks.head
Out[2]: Block(gas_data=BlockGasFee(gas_limit=69420, gas_used=0, base_fee=1000000000), consensus_data=BlockConsensus(difficulty=131072, total_difficulty=131072), hash=HexBytes('0x3b4b1109881fde4e0fe4402b7b99b865d11d56cbbafb2365072a94e42e10a6a0'), number=0, parent_hash=HexBytes('0x0000000000000000000000000000000000000000000000000000000000000000'), size=517, timestamp=1651869498)

In [3]: chain.mine(10)

In [4]: chain.blocks.height
Out[4]: 10

```


* **compilers**

Manage compilers for the current project.

```bash
$ ape plugins install vyper -y
INFO: Installing vyper...
SUCCESS: Plugin 'vyper==0.2.0' has been installed.
$ ape console

In [1]: compilers.registered_compilers
Out[1]: {'.json': <InterfaceCompiler ethpm>, '.vy': <VyperCompiler vyper>}

```
* config

The configurations for the current project, used to customize your project.


* **config**

The configurations for the current project, used to customize your project.

* **convert**

```bash
$ ape console
In [1]: convert("1 gwei", int)
Out[1]: 1000000000

In [2]: convert("1 eth", int)
Out[2]: 1000000000000000000
```
* **Contract**

Used to interact with a contract such as loading and checking balance etc.

```bash
$ ape plugins install etherscan alchemy -y
INFO: Installing etherscan...
SUCCESS: Plugin 'etherscan==0.2.0' has been installed.
INFO: Installing alchemy...
SUCCESS: Plugin 'alchemy==0.2.0' has been installed.
$ ape console --network :mainnet:alchemy

In [1]: contract = Contract("0x283Af0B28c62C092C9727F1Ee09c02CA627EB7F5")

In [2]: contract.balance
Out[2]: 14539660360031559896946

In [3]: type(contract)
Out[3]: ape.contracts.base.ContractInstance

```
* **networks**

Manages access to provider.

```bash
$ ape console
In [1]: networks.active_provider.name
Out[1]: 'test'
In [2]: exit
$ ape console --network :mainnet:alchemy
In [1]: networks.active_provider.name
Out[1]: 'alchemy'
```
* **project**

Currently active project. Best used with a contract in the contract folder.

```bash
$ape console
In [10]: project.contracts["<contract name>"].name
Out[10]: '<contract name>'
```
* **Project**

Load other projects in console to interact.