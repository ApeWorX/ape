// SPDX-License-Identifier: MIT
pragma solidity ^0.6.0;

contract HelloWorld {
    address public owner;

    constructor() public {
        owner = msg.sender;
    }
}
