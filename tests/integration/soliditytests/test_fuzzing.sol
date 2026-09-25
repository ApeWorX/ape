// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8;

import {IERC20} from "openzeppelin/contracts/token/ERC20/IERC20.sol";

contract FuzzTest {
    /// @custom:ape-fuzzer-max-examples 200
    /// @custom:ape-fuzzer-deadline 500
    function test_with_fuzzing(uint256 a) external {
        require(a != 29678634502528050652056023465820843, "Found a rare bug!");
    }

    /// @custom:ape-fuzzer-deadline 1000
    /// @custom:ape-check-emits
    /// - token.Approval(owner=msg.sender, spender=other, value=amount)
    function test_token_approvals(IERC20 token, address other, uint256 amount) external {
        require(token.approve(other, amount));
        require(token.allowance(msg.sender, other) == amount);
    }
}
