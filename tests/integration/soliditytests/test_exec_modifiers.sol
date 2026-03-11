// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8;

import {ERC20} from "openzeppelin/contracts/token/ERC20/ERC20.sol";

contract ExecTest {
    function test_default_executor(address deployer, ERC20 token, address other) external {
        require(deployer == msg.sender);

        // NOTE: Will fail if not exec'd with delegatecall,
        //       because initial balance was minted to default executor
        require(token.balanceOf(deployer) == 1000);
        require(token.balanceOf(other) == 0);

        token.transfer(other, 1000);

        require(token.balanceOf(deployer) == 0);
        require(token.balanceOf(other) == 1000);
    }

    /// @custom:ape-test-after test_default_executor
    /// @custom:ape-test-executor other
    function test_prank_executor(address deployer, ERC20 token, address other) external {
        require(other == msg.sender);

        require(token.balanceOf(deployer) == 0);
        require(token.balanceOf(other) == 1000);

        token.approve(deployer, 1000);

        require(token.balanceOf(deployer) == 0);
        require(token.balanceOf(other) == 1000);
    }

    /// @custom:ape-test-after test_prank_executor
    function test_default_executor_again(address deployer, ERC20 token, address other) external {
        require(deployer == msg.sender);

        require(token.balanceOf(deployer) == 0);
        require(token.balanceOf(other) == 1000);

        token.transferFrom(other, deployer, 1000);

        require(token.balanceOf(deployer) == 1000);
        require(token.balanceOf(other) == 0);
    }
}
