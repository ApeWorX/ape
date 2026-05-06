// SPDX-License-Identifier: MIT
pragma solidity ^0.8.0;

// Minimal mock of aragonOS AppProxyUpgradeable for proxy-detection tests.
// https://github.com/aragon/aragonOS/blob/master/contracts/apps/AppProxyUpgradeable.sol

interface IAragonKernel {
    function getApp(bytes32 namespace, bytes32 name) external view returns (address);
}

contract AragonKernelMock {
    // namespace => appId => implementation.
    mapping(bytes32 => mapping(bytes32 => address)) private apps;

    function setApp(bytes32 namespace, bytes32 appId, address app) external {
        apps[namespace][appId] = app;
    }

    function getApp(bytes32 namespace, bytes32 appId) external view returns (address) {
        return apps[namespace][appId];
    }
}

contract AragonAppProxyUpgradeable {
    bytes32 internal constant KERNEL_POSITION = keccak256("aragonOS.appStorage.kernel");
    bytes32 internal constant APP_ID_POSITION = keccak256("aragonOS.appStorage.appId");
    bytes32 internal constant APP_BASES_NAMESPACE = keccak256("base");

    constructor(address kernel, bytes32 appId) {
        bytes32 kernelSlot = KERNEL_POSITION;
        bytes32 appIdSlot = APP_ID_POSITION;
        assembly {
            sstore(kernelSlot, kernel)
            sstore(appIdSlot, appId)
        }
    }

    fallback() external payable {
        bytes32 kernelSlot = KERNEL_POSITION;
        bytes32 appIdSlot = APP_ID_POSITION;
        address kernel;
        bytes32 appId;
        assembly {
            kernel := sload(kernelSlot)
            appId := sload(appIdSlot)
        }

        address impl = IAragonKernel(kernel).getApp(APP_BASES_NAMESPACE, appId);
        assembly {
            calldatacopy(0, 0, calldatasize())
            let success := delegatecall(gas(), impl, 0, calldatasize(), 0, 0)
            returndatacopy(0, 0, returndatasize())
            switch success
            case 0 {
                revert(0, returndatasize())
            }
            default {
                return(0, returndatasize())
            }
        }
    }
}
