// SPDX-License-Identifier: MIT
pragma solidity ^0.8.4;

contract RawDeployer {
    event Deployed(address addr);

    function deploy(bytes memory code) external returns (address addr) {
        assembly {
            addr := create(0, add(code, 0x20), mload(code))
        }
        require(addr != address(0), "raw deploy failed");
        emit Deployed(addr);
    }
}
