// SPDX-License-Identifier: GPL-3.0
pragma solidity ^0.8.4;

import "./HasError.sol";

contract HasErrorDeployer {
    HasError public target;

    constructor() {
        target = new HasError(1);
    }
}

contract HasErrorCaller {
    HasError public target;

    constructor() {
        target = new HasErrorDeployer().target();
    }

    function callWithdraw() public {
        target.withdraw();
    }
}
