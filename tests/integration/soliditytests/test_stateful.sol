// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8;

interface Secret {
    function add(uint256 a) external;
    function sub(uint256 a, uint256 b) external;
    function check() external view;
}

/// @custom:ape-fuzzer-max-examples 100
/// @custom:ape-stateful-step-count 50
/// @custom:ape-stateful-bundles a b c
contract StatefulTest {
    /// @custom:ape-stateful-targets a
    function initialize_bundleA() external returns (uint256[10] memory) {
        // NOTE: Just using static array to return a literal
        //       (as Solidity automatically casts it)
        return [
            uint256(1),
            uint256(2),
            uint256(3),
            uint256(5),
            uint256(7),
            uint256(11),
            uint256(13),
            uint256(17),
            uint256(19),
            uint256(23)
        ];
    }

    /// @custom:ape-stateful-targets b
    function rule_add(Secret secret, uint256 a) external returns (uint256) {
        secret.add(a);

        return a % 100;
    }

    /// @custom:ape-stateful-consumes b
    function rule_subtract(Secret secret, uint256[] calldata a, uint256 b) external {
        // NOTE: This will likely fail after a few calls

        for (uint256 idx = 0; idx < a.length; idx++) {
            secret.sub(a[idx], b);
        }
    }
}
