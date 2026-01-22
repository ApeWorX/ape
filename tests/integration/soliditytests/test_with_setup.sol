// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8;

contract SetupTest {
    uint256 store;

    function setUp() external {
        store++;
    }

    function test_setup_works() external {
        require(store == 1);
    }

    function test_setup_works_2nd_time() external {
        require(store == 1);
    }
}
