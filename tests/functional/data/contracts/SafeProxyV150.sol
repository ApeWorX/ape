// SPDX-License-Identifier: LGPL-3.0-only

pragma solidity >=0.7.0 <0.9.0;


// Copied from https://github.com/safe-global/safe-smart-account/blob/v1.5.0/contracts/proxies/SafeProxy.sol

contract SafeProxyV150 {
    // Singleton always needs to be first declared variable, to ensure that it is at the same location in the contracts to which calls are delegated.
    address internal singleton;

    /**
     * @notice Constructor function sets address of singleton contract.
     * @param _singleton Singleton address.
     */
    constructor(address _singleton) {
        require(_singleton != address(0), "Invalid singleton address provided");
        singleton = _singleton;
    }

    /// @dev Fallback function forwards all transactions and returns all received return data.
    fallback() external payable {
        /* solhint-disable no-inline-assembly */
        assembly {
            let _singleton := sload(0)
            // 0xa619486e == uint32(bytes4(keccak256("masterCopy()"))).
            if eq(shr(224, calldataload(0)), 0xa619486e) {
                mstore(0x6c, shl(96, _singleton))
                return(0x60, 0x20)
            }
            calldatacopy(0, 0, calldatasize())
            let success := delegatecall(gas(), _singleton, 0, calldatasize(), 0, 0)
            returndatacopy(0, 0, returndatasize())
            if iszero(success) {
                revert(0, returndatasize())
            }
            return(0, returndatasize())
        }
        /* solhint-enable no-inline-assembly */
    }
}
