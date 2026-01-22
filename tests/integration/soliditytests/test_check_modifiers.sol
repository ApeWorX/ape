// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8;

import {IERC20} from "openzeppelin/contracts/token/ERC20/IERC20.sol";

contract CheckerTest {
    /// @custom:ape-check-reverts "This error gets raised"
    function test_reverts_with() external {
        revert("This error gets raised");
    }

    /// @custom:ape-check-emits
    /// - token.Approval(owner=self, spender=executor, value=100_000)
    /// - token.Approval(spender=executor, value=10_000)
    /// - token.Approval(owner=self, spender=executor)
    /// - token.Approval(owner=self, value=100)
    /// - token.Approval(value=10)
    /// - token.Approval()
    function test_emits(IERC20 token, address executor) external {
        token.approve(executor, 100_000);
        token.approve(executor, 10_000);
        token.approve(executor, 1_000);
        token.approve(executor, 100);
        token.approve(executor, 10);
        token.approve(executor, 1);
    }
}
