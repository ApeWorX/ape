// SPDX-License-Identifier: UNLICENSED
pragma solidity ^0.8;

/// @custom:ape-fuzzer-max-examples 100
/// @custom:ape-stateful-step-count 50
/// @custom:ape-stateful-bundles a b c
contract StatefulTest {
    uint256 public secret;

    function setUp() external {
        secret = 703895692105206524502680346056234;
    }

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

    /// @custom:ape-stateful-precondition this.secret() + a + b < 2 ** 256
    /// @custom:ape-stateful-targets b
    function rule_add(uint256 a) external returns (uint256) {
        // NOTE: Due to precondition, will **never** fail
        secret += a;

        return a % 100;
    }

    /// @custom:ape-stateful-consumes b
    function rule_subtract(uint256[] calldata a, uint256 b) external {
        // NOTE: This will likely fail after a few calls

        for (uint256 idx = 0; idx < a.length; idx++) {
            secret -= a[idx] % b;
        }
    }

    function invariant_secret_not_found() external view {
        require(secret != 2378945823475283674509246524589);
    }
}
