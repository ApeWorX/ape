# Reverts

Reverts occur when a transaction or call fails for any reason.
In the case of EVM networks, reverts result in funds being returned to the sender (besides network-fees) and contract state changes unwinding.
Typically, in smart-contracts, user-defined reverts occur from `assert` statements in Vyper and `require` statements in Solidity.

Here is a Vyper example of an `assert` statement:

```python
assert msg.sender == self.owner, "!authorized"
```

The string `"!authorized"` after the assertion is the revert-message that gets forwarded to the user.

In solidity, a `require` statement looks like:

```solidity
require(msg.sender == owner, "!authorized");
```

In Ape, reverts automatically become Python exceptions.
When [interacting with a contract](./contracts.html#contract-interaction) and encountering a revert, your program will crash and you will see a stacktrace showing you where the revert occurred.
For example, assume you have contract instance variable `contract` with a Vyper method called `setNumber()`, and it reverts when the user is not the owner of the contract.
Calling it may look like:

```python
receipt = contract.setNumber(123, sender=not_owner)
```

And when it fails, Ape shows a stacktrace like this:

```shell
  File "$HOME/ApeProjects/ape-project/scripts/fail.py", line 8, in main
    receipt = contract.setNumber(5, sender=not_owner)
              ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "$HOME/ApeProjects/ape-project/contracts/VyperContract.vy", line 98, in 
setNumber
    assert msg.sender == self.owner, "!authorized"
    ^^^^^^^^^^^^^^^^^^^^^^^

ERROR: (ContractLogicError) !authorized
```

One way to handle exceptions is to simply use `try:` / `except:` blocks:

```python
from ape.exceptions import ContractLogicError

try:
    receipt = contract.setNumber(123, sender=not_owner)
except ContractLogicError as err:
    receipt = None
    print(f"The transaction failed: {err}")
# continue on!
```

If you wish to allow reverts without having Ape raise exceptions, use the `raise_on_revert=False` flag:

```python
>>> receipt = contract.setNumber(123, sender=not_owner, raise_on_revert=False)
>>> receipt.failed
True
>>> receipt.error
ContractLogicError('!authorized')
```

## Dev Messages

Dev messages allow smart-contract authors to save gas by avoiding revert-messages.
If you are using a provider that supports tracing features and a compiler that can detect `dev` messages, and you encounter a revert without a revert-message but it has a dev-message, Ape will show the dev-message:

```python
assert msg.sender == self.owner  # dev: !authorized"
```

And you will see a similar stacktrace as if you had used a revert-message.

In Solidity, it might look like this:

```solidity
require(msg.sender == owner);  // @dev !authorized
```

## Custom Errors

As of Solidity 0.8.4, custom errors have been introduced to the ABI.
In Ape, custom errors are available on contract-instances.
For example, if you have a contract like:

```solidity
// SPDX-License-Identifier: GPL-3.0
pragma solidity ^0.8.4;

error Unauthorized(address unauth_address);

contract MyContract {
    address payable owner = payable(msg.sender);
    function withdraw() public {
        if (msg.sender != owner)
            revert Unauthorized(msg.sender);
        owner.transfer(address(this).balance);
    }
}
```

And if you have an instance of this contract assigned to variable `contract`, you can reference the custom exception by doing:

```python
contract.Unauthorized
```

When invoking `withdraw()` with an unauthorized account using Ape, you will get an exception similar to those from `require()` statements, a subclass of `ContractLogicError`:

```python
contract.withdraw(sender=hacker)  # assuming 'hacker' refers to the account without authorization.
```

## Built-in Errors

Besides user-defined `ContractLogicError`s, there are also builtin-errors from compilers, such as bounds-checking of arrays or paying a non-payable method, etc.
These are also `ContractLogicError` sub-classes.
Sometimes, compiler plugins such as `ape-vyper` or `ape-solidity` export these error classes for you to use.

```python
from ape import accounts, Contract
from ape_vyper.exceptions import FallbackNotDefinedError

my_contract = Contract("0x...")
account = accounts.load("test-account")

try:
    my_contract(sender=account)
except FallbackNotDefinedError:
    print("fallback not defined")
```

Next, learn how to test your contracts' errors using the `ape.reverts` context-manager in the [testing guide](./testing.html#testing-transaction-reverts).
