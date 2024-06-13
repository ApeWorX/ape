# Accounts

Accounts in Ape come from [AccountAPI](../methoddocs/api.html#ape.api.accounts.AccountAPI) implementations (e.g. from plugins).
There are typically two types of accounts:

1. Test accounts
2. Live network accounts

Test accounts are useful for local network testing and debugging contracts.
Live network accounts are for interacting with live blockchains and should be secured.

To learn more about Ethereum accounts, see [the Ethereum documentation](https://ethereum.org/en/developers/docs/accounts/).

## Test Accounts

Ape ships with pytest fixtures to assist in writing your tests.

### Use test accounts in tests

Pre-funded test accounts are accessible via the [accounts fixture](./testing.html#accounts-fixture).

```python
def test_my_contract_method(accounts):
    sender = accounts[0]
    ...
```

### Use test accounts outside of tests

To access the same prefunded accounts in your scripts or console, use the root `accounts` object and the [test_accounts](../methoddocs/managers.html#ape.managers.accounts.AccountManager.test_accounts) property:

```{eval-rst}
.. doctest::

  >>> from ape import accounts

  >>> sender = accounts.test_accounts[0]

```

You can configure your test accounts using your `ape-config.yaml` file:

```yaml
test:
  mnemonic: test test test test test test test test test test test junk
  number_of_accounts: 5
```

```{warning}
NEVER put a seed phrase with real funds here.
```

The accounts generated from this seed are solely for testing and debugging purposes.

### Creating new test accounts

You can create a new test account by doing the following:

```{eval-rst}
.. doctest::

  >>> from ape import accounts

  >>> account = accounts.test_accounts.generate_test_account()
```

```{note}
Creating a new test account means it will be unfunded by default.
```

Learn more about test accounts from the [testing guide](./testing.html#accounts-fixture).

If your testing provider supports this feature, it is possible to directly set the balances of any address by performing the following action:

```python
account.balance += int(1e18)  # Gives `account` 1 Ether
```

### Default Sender Support

In order to eliminate the usage of sender in contract calls, you can use `use_sender` context manager.

```python
with accounts.use_sender(0): # Use first account from test mnemonic
  contract.myFunction(1)

with accounts.use_sender("<address>"): # Impersonate an account
  contract.myFunction(1)

with accounts.use_sender(a): # a is a `TestAccountAPI` object
  contract.myFunction(1)
```

## Live Network Accounts

When using live networks, you need to get your accounts into Ape.
To get your accounts in Ape, you must use an `accounts` plugin.
Ape ships with a keyfile-based account plugin, but you can use any account plugin such as `ape-ledger`, `ape-trezor`, or a third-party plugin.

### Keyfile Accounts

Ape ships with a keyfile-based account plugin that lets you import and generate accounts.
The premise of the plugin is that accounts are stored locally on your computer in the `$HOME/.ape/accounts` directory following the `keyfile` structure.
Under-the-hood, this structure comes from the [eth-keyfile library](https://github.com/ethereum/eth-keyfile) via the [eth-account](https://eth-account.readthedocs.io/en/stable/eth_account.html) package.
When Ape creates the keyfile, either from import or account-generation (described below!), it prompts you for a passphrase to use for encrypting the keyfile, similarly to how you would use a password in browser-based wallets.
The keyfile stores the private key in an encrypted-at-rest state, which maximizes security of the locally-stored key material.

The `ape-accounts` core plugin lets you use keyfile-based account to sign messages and transactions.
When signing a message or transaction using an account from `ape-accounts`, you will be prompted to enter the passphrase you specified when importing or generating that account.

All the available CLI commands for this account's plugin can be found [here](../commands/accounts.html).

#### Generating New Accounts

You can [generate](../commands/accounts.html#accounts-generate) an account:

```bash
ape accounts generate <ALIAS>
```

Ape will prompt you for entropy which is used to increase randomness when creating your account.
Ape will then prompt you whether you want to show your mnemonic.
If you do not want to see your mnemonic you can select `n`.
Alternatively, you can use the `--hide-mnemonic` option to skip the prompt.

```bash
ape accounts generate <ALIAS> --hide-mnemonic
```

If you elected to show your mnemonic Ape will then show you your newly generated mnemonic.
Ape will then prompt you for a passphrase which you will need to enter twice to confirm.
This passphrase is used to encrypt your account on disk, for extra security.
You will be prompted for it each time you load your account, so make sure to remember it.
After entering the passphrase Ape will then show you your new account address, HDPath, and account alias.
If you want to use a custom HDPath, use the `--hd-path` option:

```bash
ape accounts generate <ALIAS> --hd-path <HDPATH>
```

If you do not use the `--hd-path` option, Ape will use the default HDPath of (Ethereum network, first account).
If you want to use a custom mnemonic phrase word length, use the `--word-count` option:

```bash
ape accounts generate <ALIAS> --word-count <WORDCOUNT>
```

If you do not use the `--word-count` option, Ape will use the default word count of 12.
You can use all of these together or separately to control the way Ape creates and displays your account information.

This same functionality is also scriptable with the same inputs as the `generate` command:

```python
from ape_accounts import generate_account

account, mnemonic = generate_account("my-account", "mySecureP@ssphrase")

print(f'Save your mnemonic: {mnemonic}')
print(f'Your new account address is: {account.address}')
```

See the [documentation for `generate_account()`](../methoddocs/ape_accounts.html#ape_accounts.generate_account) for more options.

#### Importing Existing Accounts

If you already have an account and wish to import it into Ape (say, from Metamask), you can use the [import command](../commands/accounts.html#accounts-import):

```bash
ape accounts import <ALIAS>
```

It will prompt you for the private key.
If you need help exporting your private key from Metamask, see [this guide](https://metamask.zendesk.com/hc/en-us/articles/360015289632-How-to-export-an-account-s-private-key).
You can also import accounts from mnemonic seed by using the `--use-mnemonic` flag:

```bash
ape accounts import <ALIAS> --use-mnemonic
```

It will then prompt you for the [mnemonic seed](https://en.bitcoin.it/wiki/Seed_phrase).
If you need help finding your mnemonic seed (Secret Recovery Phrase) in Metamask, see [this guide](https://metamask.zendesk.com/hc/en-us/articles/360015290032-How-to-reveal-your-Secret-Recovery-Phrase).
In addition, you can also use a custom HDPath by using the `--hd-path` option:

```bash
ape accounts import <ALIAS> --use-mnemonic --hd-path <HDPATH>
```

If you use the `--hd-path` option, you will need to pass the [HDPath](https://help.myetherwallet.com/en/articles/5867305-hd-wallets-and-derivation-paths) you'd like to use as an argument in the command.
If you do not use the `--hd-path` option, Ape will use the default HDPath of (Ethereum network, first account).

You can import an account programmatically using a seed phrase [using `import_account_from_mnemonic()`](../methoddocs/ape_accounts.html#ape_accounts.import_account_from_mnemonic):

```python
from ape_accounts import import_account_from_mnemonic

alias = "my-account"
passphrase = "my$ecurePassphrase"
mnemonic = "test test test test test test test test test test test junk"

account = import_account_from_mnemonic(alias, passphrase, mnemonic)

print(f'Your imported account address is: {account.address}')
```

Or using a raw private key [using `import_account_from_private_key()`](../methoddocs/ape_accounts.html#ape_accounts.import_account_from_private_key):

```python
import os
from ape_accounts import import_account_from_private_key

alias = "my-account"
passphrase = "my SecurePassphrase"
private_key = os.urandom(32).hex()

account = import_account_from_private_key(alias, passphrase, private_key)

print(f'Your imported account address is: {account.address}')
```

#### Exporting Accounts

You can also [export](../commands/accounts.html#accounts-export) the private key of an account:

```bash
ape accounts export <ALIAS>
```

Ape will ask you for the password to the account and then give you the private key of that account.
You can then use that private key with [import](../commands/accounts.html#accounts-import).
You can alternatively load the private key into [Metamask wallet](https://metamask.zendesk.com/hc/en-us/articles/360015489331-How-to-import-an-account#h_01G01W07NV7Q94M7P1EBD5BYM4).
Then, in your scripts, you can [load](../methoddocs/managers.html#ape.managers.accounts.AccountManager.load) an account:

```python
from ape import accounts

account = accounts.load("<ALIAS>")
```

### Default Sender Support

In order to reduce repetition of adding `sender` in your contract calls, you can use `use_sender` context manager.

```python
with accounts.use_sender(0):
  contract.myFunction(1)

with accounts.use_sender("<address>"):
  contract.myFunction(1)

with accounts.use_sender("<alias>"):
  contract.myFunction(1)

with accounts.use_sender(a): # a is a `AccountAPI` object
  contract.myFunction(1)
```

## Signing Messages

You can sign messages with your accounts in Ape.
To do this, use the [sign_message](../methoddocs/api.html#ape.api.accounts.AccountAPI.sign_message) API.

```python
from ape import accounts
from eth_account.messages import encode_defunct

account = accounts.load("<ALIAS>")
message = encode_defunct(text="Hello Apes!")
signature = account.sign_message(message)
```

```{note}
Ape's `sign_message` API intentionally accepts `Any` as the message argument type.
```

Account plugins decide what data-types to support.
Most Ethereum account plugins, such as `ape-account`, are able to sign messages like the example above.
However, you can also provide other types, such as a `str` directly:

```python
from ape import accounts

account = accounts.load("<ALIAS>")
signature = account.sign_message("Hello Apes!")
```

### EIP-712

Some account plugins are able to sign EIP-712 structured message types by utilizing the `eip712` package.
Here is an example with custom EIP-712 classes:

```python
from ape import accounts
from eip712.messages import EIP712Message, EIP712Type

class Person(EIP712Type):
    name: "string"
    wallet: "address"

class Mail(EIP712Message):
    _chainId_: "uint256" = 1
    _name_: "string" = "Ether Mail"
    _verifyingContract_: "address" = "0xCcCCccccCCCCcCCCCCCcCcCccCcCCCcCcccccccC"
    _version_: "string" = "1"

    sender: Person
    receiver: Person

alice = Person(name="Alice", wallet="0xCD2a3d9F938E13CD947Ec05AbC7FE734Df8DD826")
bob = Person("Bob", "0xB0B0b0b0b0b0B000000000000000000000000000")
message = Mail(sender=alice, receiver=bob)

account = accounts.load("<ALIAS>")
account.sign_message(message)
```

### Verifying Signature

Verify the signatures on your signed messages by using the [recover_signer](../methoddocs/types.html#ape.types.signatures.recover_signer) function or the [check_signature](../methoddocs/api.html#ape.api.accounts.AccountAPI.check_signature) function:

```python
from ape import accounts
from ape.types.signatures import recover_signer
from eth_account.messages import encode_defunct

account = accounts.load("<ALIAS>")
message = encode_defunct(text="Hello Apes!")
signature = account.sign_message(message)

# Validate the signature by recovering the signer and asserting it is equal to the sender.
recovered_signer = recover_signer(message, signature)
assert recovered_signer == account.address

# NOTE: You can also use the `check_signature` method on an account, which returns a bool.
assert account.check_signature(message, signature)
```

## Automation

If you use your keyfile accounts in automation, such as CI/CD, you may need to programmatically unlock them and enable auto-sign.
To do this, use a special environment variable for the account's passphrase:

```bash
export APE_ACCOUNTS_<alias>_PASSPHRASE="a"
```

Where `<alias>` is the name of the account you want to use.
Now, you can use your account to make any transactions without subsequently providing your passphrase.

```py
from ape import accounts
from eth_account.messages import encode_defunct

account = accounts.load("<ALIAS>")
account.set_autosign(True)

# Now, you will not be prompted to sign messages or transactions
message = encode_defunct(text="Hello Apes!")
signature = account.sign_message(message)
```

```{note}
Alternatively, you may use the `passphrase=` kwarg on methods `account.set_autosign()` and `account.unlock()`, but we highly recommend using the environment variable approach to avoid accidentally leaking your passphrase.
```

## Hardware Wallets

Because of the plugin system in Ape, we are able to support other types of accounts including hardware wallet accounts.
Check out these plugins:

- [ape-ledger](https://github.com/ApeWorX/ape-ledger)
- [ape-trezor](https://github.com/ApeWorX/ape-trezor)

To install one of these plugins, do the following:

```bash
ape plugins install ledger
```
