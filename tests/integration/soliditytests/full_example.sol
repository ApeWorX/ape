// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8;

// NOTE: This mirrors the full example from `docs/userguides/contract_tests.md`

import {ERC20} from "openzeppelin/contracts/token/ERC20/ERC20.sol";

/// @custom:ape-fuzzer-max-examples 10
/// @custom:ape-stateful-step-count 5
/// @custom:ape-stateful-bundles holder
contract TokenStatefulTest {
    // TODO: How do we do this with the executor trick? Separate storage?
    uint256 balanceOf_sum = 0;

    /// @custom:ape-stateful-targets holder
    function initialize_holders(ERC20 token, address[] memory accounts) external returns (address[] memory) {
        for (uint256 idx = 0; idx < accounts.length; idx++) {
            token.mint(accounts[idx], 1000000);
            balanceOf_sum += 1000000;
        }

        return accounts;
    }

    /// @custom:ape-test-executor holder
    /// @custom:ape-stateful-targets holder
    function rule_transfer(ERC20 token, address holder, address account, uint256 bips) external returns (address) {
        uint256 amount = (token.balanceOf(holder) * bips) / 10000;

        token.transfer(account, amount);

        return account;
    }

    /// @custom:ape-stateful-targets holder
    function rule_mint(ERC20 token, address account, uint256 bips) external returns (address) {
        uint256 amount = (token.totalSupply() * bips) / 10000;
        token.mint(account, amount);

        // NOTE: Keep track of newly minted balance in shadow variable
        balanceOf_sum += amount;

        // NOTE: Add `account` to `holder` Bundle.
        return account;
    }

    function invariant_total_supply() external view {
        require(token.totalSupply() == balanceOf_sum);
    }
}
