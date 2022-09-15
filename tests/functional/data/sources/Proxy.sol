pragma solidity ^0.8.4;

contract Proxy {

    address public implementation;
    uint256 public proxyType = 2;

    constructor(address impl) {
        implementation = impl;
    }

    function setImplementation(address implementation_) public {
        implementation = implementation_;
    }
}
