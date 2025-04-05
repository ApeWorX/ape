// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8.0;

contract SolFallbackAndReceive {
    fallback() external {
    }

    event Received(address, uint);
    receive() external payable {
        emit Received(msg.sender, msg.value);
    }
}
