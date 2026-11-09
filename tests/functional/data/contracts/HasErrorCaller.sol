// SPDX-License-Identifier: GPL-3.0
pragma solidity ^0.8.4;

interface IHasError {
    function withdraw() external;
}

contract HasErrorCaller {
    function callWithdraw(IHasError target) public {
        target.withdraw();
    }
}
