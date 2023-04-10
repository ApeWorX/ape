// SPDX-License-Identifier: GPL-3.0
pragma solidity ^0.8.4;

error Unauthorized(address addr, uint256 counter);
error OtherError(address foo);

contract HasError {
    address payable owner = payable(msg.sender);

    function withdraw() public {
        if (msg.sender != owner)
            revert Unauthorized(msg.sender, 123);

        if (msg.sender == address(0))
            revert OtherError(msg.sender);

        owner.transfer(address(this).balance);
    }
    // ...
}
