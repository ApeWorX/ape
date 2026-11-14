// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8;

contract MarkerTest {
    /// @custom:ape-mark-xfail "Should not execute"
    function test_xfail() external {
        revert("Fails for any reason");
    }

    /// @custom:ape-mark-parametrize i
    /// - 1
    /// - 2
    /// - 3
    function test_parametrizing(uint256 i) external {
        require(i > 0);
    }

    /// @custom:ape-mark-parametrize a,b
    /// - (0x1, 1)
    /// - (0x2, 2)
    /// - (0x3, 3)
    function test_parametrizing_multiple_args(address a, uint256 b) external {
        require(uint256(uint160(a)) == b);
    }
}
