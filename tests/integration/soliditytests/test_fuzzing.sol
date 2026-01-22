// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8;

import {IERC20} from "openzeppelin/contracts/token/ERC20/IERC20.sol";

contract FuzzTest {
    /// @custom:ape-fuzzer-max-examples 200
    function test_with_fuzzing(uint256 a) external {
        require(a != 29678634502528050652056023465820843, "Found a rare bug!");
    }

    /// @custom:ape-fuzzer-deadline 1000
    function test_token_approvals(IERC20 token, uint256 amount) external {
        require(token.approve(msg.sender, amount));
        require(token.allowance(address(this), msg.sender) == amount);
    }
}
