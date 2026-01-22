// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8;

contract BasicTest {
    function test_it_works() external {
        require(1 + 1 == 2, "We can do tests in solidity!");
    }

    function test_using_fixtures(address[] calldata accounts, address executor) external {
        for (uint256 idx = 0; idx < accounts.length; idx++) {
            require(accounts[idx].balance >= 10 ** 18);
        }

        require(executor == msg.sender);

        bool executor_in_accounts = false;
        for (uint256 idx = 0; idx < accounts.length; idx++) {
            if (executor == accounts[idx]) {
                executor_in_accounts = true;
                break;
            }
        }
        require(executor_in_accounts);
    }
}
