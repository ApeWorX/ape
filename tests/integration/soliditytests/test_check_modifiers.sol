// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8;

import {IERC20} from "openzeppelin/contracts/token/ERC20/IERC20.sol";

contract CheckerTest {
    /// @custom:ape-check-reverts It works!
    function test_it_raises() external {
        revert("It works!");
    }

    /// @custom:ape-check-emits
    /// - token.Approval(owner=msg.sender, spender=other, value=100_000)
    /// - token.Approval(spender=other, value=10_000)
    /// - token.Approval(owner=msg.sender, spender=other)
    /// - token.Approval(owner=msg.sender, value=100)
    /// - token.Approval(value=10)
    /// - token.Approval()
    function test_emits(IERC20 token, address other) external {
        token.approve(other, 100_000);
        token.approve(other, 10_000);
        token.approve(other, 1_000);
        token.approve(other, 100);
        token.approve(other, 10);
        token.approve(other, 1);
    }
}
