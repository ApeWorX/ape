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
Pre-funded test accounts are accessible via the [accounts fixture](./testing.html#accounts-fixture).

```python
def test_my_contract_method(accounts):
    sender = accounts[0]
    ...
```

To access the same prefunded accounts in your scripts or console, use the root `accounts` object and the [test_accounts](../methoddocs/managers.html#ape.managers.accounts.AccountManager.test_accounts) property:

```python
from ape import accounts

sender = accounts.test_accounts[0]
```

You can configure your test accounts using your `ape-config.yaml` file:

```yaml
test:
  mnemonic: test test test test test test test test test test test junk
  number_of_accounts: 5
```

**WARN**: NEVER put a seed phrase with real funds here.
The accounts generated from this seed are solely for testing and debugging purposes.

You can create a new test account by doing the following:

```python
account = accounts.test_accounts.generate_test_account()
```

**NOTE**: Creating a new test account means it will be unfunded by default.

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
Ape ships with a keyfile accounts plugin to assist with this.
All the available CLI commands for this accounts plugin can be found [here](../commands/accounts.html).

For example, you can [generate](../commands/accounts.html#accounts-generate) an account:

```bash
ape accounts generate <ALIAS>
```

Ape will prompt you for entropy which is used to increase randomness when creating your account.

Ape will then prompt you whether you want to show your mnemonic.

If you do not want to see your mnemonic you can select `n`.

Alternatively you can use the `--hide-mnemonic` option to skip the prompt.

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

If you already have an account and you wish to import it into Ape (say, from Metamask), you can use the [import command](../commands/accounts.html#accounts-import):

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

## Automation

If you use your keyfile accounts in automation, such as CI/CD, you may need to programmatically unlock them and enable autosign.
**WARNING**: We don't recommend using this approach but it is possible due to sometimes being needed.
Ensure you are using a secure environment and are aware of what you are doing.

```python
from ape import accounts
from eth_account.messages import encode_defunct

account = accounts.load("<ALIAS>")
account.set_autosign(True, passphrase="<PASSPHRASE>")

# Now, you will not be prompted to sign messages or transactions
message = encode_defunct(text="Hello Apes!")
signature = account.sign_message(message)
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
