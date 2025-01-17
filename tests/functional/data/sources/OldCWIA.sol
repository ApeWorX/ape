// SPDX-License-Identifier: Unlicense
pragma solidity >=0.4.23 ^0.8.0;

// lib/ds-test/src/test.sol

// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.

// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

contract DSTest {
    event log                    (string);
    event logs                   (bytes);

    event log_address            (address);
    event log_bytes32            (bytes32);
    event log_int                (int);
    event log_uint               (uint);
    event log_bytes              (bytes);
    event log_string             (string);

    event log_named_address      (string key, address val);
    event log_named_bytes32      (string key, bytes32 val);
    event log_named_decimal_int  (string key, int val, uint decimals);
    event log_named_decimal_uint (string key, uint val, uint decimals);
    event log_named_int          (string key, int val);
    event log_named_uint         (string key, uint val);
    event log_named_bytes        (string key, bytes val);
    event log_named_string       (string key, string val);

    bool public IS_TEST = true;
    bool public failed;

    address constant HEVM_ADDRESS =
        address(bytes20(uint160(uint256(keccak256('hevm cheat code')))));

    modifier mayRevert() { _; }
    modifier testopts(string memory) { _; }

    function fail() internal {
        failed = true;
    }

    modifier logs_gas() {
        uint startGas = gasleft();
        _;
        uint endGas = gasleft();
        emit log_named_uint("gas", startGas - endGas);
    }

    function assertTrue(bool condition) internal {
        if (!condition) {
            emit log("Error: Assertion Failed");
            fail();
        }
    }

    function assertTrue(bool condition, string memory err) internal {
        if (!condition) {
            emit log_named_string("Error", err);
            assertTrue(condition);
        }
    }

    function assertEq(address a, address b) internal {
        if (a != b) {
            emit log("Error: a == b not satisfied [address]");
            emit log_named_address("  Expected", b);
            emit log_named_address("    Actual", a);
            fail();
        }
    }
    function assertEq(address a, address b, string memory err) internal {
        if (a != b) {
            emit log_named_string ("Error", err);
            assertEq(a, b);
        }
    }

    function assertEq(bytes32 a, bytes32 b) internal {
        if (a != b) {
            emit log("Error: a == b not satisfied [bytes32]");
            emit log_named_bytes32("  Expected", b);
            emit log_named_bytes32("    Actual", a);
            fail();
        }
    }
    function assertEq(bytes32 a, bytes32 b, string memory err) internal {
        if (a != b) {
            emit log_named_string ("Error", err);
            assertEq(a, b);
        }
    }
    function assertEq32(bytes32 a, bytes32 b) internal {
        assertEq(a, b);
    }
    function assertEq32(bytes32 a, bytes32 b, string memory err) internal {
        assertEq(a, b, err);
    }

    function assertEq(int a, int b) internal {
        if (a != b) {
            emit log("Error: a == b not satisfied [int]");
            emit log_named_int("  Expected", b);
            emit log_named_int("    Actual", a);
            fail();
        }
    }
    function assertEq(int a, int b, string memory err) internal {
        if (a != b) {
            emit log_named_string("Error", err);
            assertEq(a, b);
        }
    }
    function assertEq(uint a, uint b) internal {
        if (a != b) {
            emit log("Error: a == b not satisfied [uint]");
            emit log_named_uint("  Expected", b);
            emit log_named_uint("    Actual", a);
            fail();
        }
    }
    function assertEq(uint a, uint b, string memory err) internal {
        if (a != b) {
            emit log_named_string("Error", err);
            assertEq(a, b);
        }
    }
    function assertEqDecimal(int a, int b, uint decimals) internal {
        if (a != b) {
            emit log("Error: a == b not satisfied [decimal int]");
            emit log_named_decimal_int("  Expected", b, decimals);
            emit log_named_decimal_int("    Actual", a, decimals);
            fail();
        }
    }
    function assertEqDecimal(int a, int b, uint decimals, string memory err) internal {
        if (a != b) {
            emit log_named_string("Error", err);
            assertEqDecimal(a, b, decimals);
        }
    }
    function assertEqDecimal(uint a, uint b, uint decimals) internal {
        if (a != b) {
            emit log("Error: a == b not satisfied [decimal uint]");
            emit log_named_decimal_uint("  Expected", b, decimals);
            emit log_named_decimal_uint("    Actual", a, decimals);
            fail();
        }
    }
    function assertEqDecimal(uint a, uint b, uint decimals, string memory err) internal {
        if (a != b) {
            emit log_named_string("Error", err);
            assertEqDecimal(a, b, decimals);
        }
    }

    function assertGt(uint a, uint b) internal {
        if (a <= b) {
            emit log("Error: a > b not satisfied [uint]");
            emit log_named_uint("  Value a", a);
            emit log_named_uint("  Value b", b);
            fail();
        }
    }
    function assertGt(uint a, uint b, string memory err) internal {
        if (a <= b) {
            emit log_named_string("Error", err);
            assertGt(a, b);
        }
    }
    function assertGt(int a, int b) internal {
        if (a <= b) {
            emit log("Error: a > b not satisfied [int]");
            emit log_named_int("  Value a", a);
            emit log_named_int("  Value b", b);
            fail();
        }
    }
    function assertGt(int a, int b, string memory err) internal {
        if (a <= b) {
            emit log_named_string("Error", err);
            assertGt(a, b);
        }
    }
    function assertGtDecimal(int a, int b, uint decimals) internal {
        if (a <= b) {
            emit log("Error: a > b not satisfied [decimal int]");
            emit log_named_decimal_int("  Value a", a, decimals);
            emit log_named_decimal_int("  Value b", b, decimals);
            fail();
        }
    }
    function assertGtDecimal(int a, int b, uint decimals, string memory err) internal {
        if (a <= b) {
            emit log_named_string("Error", err);
            assertGtDecimal(a, b, decimals);
        }
    }
    function assertGtDecimal(uint a, uint b, uint decimals) internal {
        if (a <= b) {
            emit log("Error: a > b not satisfied [decimal uint]");
            emit log_named_decimal_uint("  Value a", a, decimals);
            emit log_named_decimal_uint("  Value b", b, decimals);
            fail();
        }
    }
    function assertGtDecimal(uint a, uint b, uint decimals, string memory err) internal {
        if (a <= b) {
            emit log_named_string("Error", err);
            assertGtDecimal(a, b, decimals);
        }
    }

    function assertGe(uint a, uint b) internal {
        if (a < b) {
            emit log("Error: a >= b not satisfied [uint]");
            emit log_named_uint("  Value a", a);
            emit log_named_uint("  Value b", b);
            fail();
        }
    }
    function assertGe(uint a, uint b, string memory err) internal {
        if (a < b) {
            emit log_named_string("Error", err);
            assertGe(a, b);
        }
    }
    function assertGe(int a, int b) internal {
        if (a < b) {
            emit log("Error: a >= b not satisfied [int]");
            emit log_named_int("  Value a", a);
            emit log_named_int("  Value b", b);
            fail();
        }
    }
    function assertGe(int a, int b, string memory err) internal {
        if (a < b) {
            emit log_named_string("Error", err);
            assertGe(a, b);
        }
    }
    function assertGeDecimal(int a, int b, uint decimals) internal {
        if (a < b) {
            emit log("Error: a >= b not satisfied [decimal int]");
            emit log_named_decimal_int("  Value a", a, decimals);
            emit log_named_decimal_int("  Value b", b, decimals);
            fail();
        }
    }
    function assertGeDecimal(int a, int b, uint decimals, string memory err) internal {
        if (a < b) {
            emit log_named_string("Error", err);
            assertGeDecimal(a, b, decimals);
        }
    }
    function assertGeDecimal(uint a, uint b, uint decimals) internal {
        if (a < b) {
            emit log("Error: a >= b not satisfied [decimal uint]");
            emit log_named_decimal_uint("  Value a", a, decimals);
            emit log_named_decimal_uint("  Value b", b, decimals);
            fail();
        }
    }
    function assertGeDecimal(uint a, uint b, uint decimals, string memory err) internal {
        if (a < b) {
            emit log_named_string("Error", err);
            assertGeDecimal(a, b, decimals);
        }
    }

    function assertLt(uint a, uint b) internal {
        if (a >= b) {
            emit log("Error: a < b not satisfied [uint]");
            emit log_named_uint("  Value a", a);
            emit log_named_uint("  Value b", b);
            fail();
        }
    }
    function assertLt(uint a, uint b, string memory err) internal {
        if (a >= b) {
            emit log_named_string("Error", err);
            assertLt(a, b);
        }
    }
    function assertLt(int a, int b) internal {
        if (a >= b) {
            emit log("Error: a < b not satisfied [int]");
            emit log_named_int("  Value a", a);
            emit log_named_int("  Value b", b);
            fail();
        }
    }
    function assertLt(int a, int b, string memory err) internal {
        if (a >= b) {
            emit log_named_string("Error", err);
            assertLt(a, b);
        }
    }
    function assertLtDecimal(int a, int b, uint decimals) internal {
        if (a >= b) {
            emit log("Error: a < b not satisfied [decimal int]");
            emit log_named_decimal_int("  Value a", a, decimals);
            emit log_named_decimal_int("  Value b", b, decimals);
            fail();
        }
    }
    function assertLtDecimal(int a, int b, uint decimals, string memory err) internal {
        if (a >= b) {
            emit log_named_string("Error", err);
            assertLtDecimal(a, b, decimals);
        }
    }
    function assertLtDecimal(uint a, uint b, uint decimals) internal {
        if (a >= b) {
            emit log("Error: a < b not satisfied [decimal uint]");
            emit log_named_decimal_uint("  Value a", a, decimals);
            emit log_named_decimal_uint("  Value b", b, decimals);
            fail();
        }
    }
    function assertLtDecimal(uint a, uint b, uint decimals, string memory err) internal {
        if (a >= b) {
            emit log_named_string("Error", err);
            assertLtDecimal(a, b, decimals);
        }
    }

    function assertLe(uint a, uint b) internal {
        if (a > b) {
            emit log("Error: a <= b not satisfied [uint]");
            emit log_named_uint("  Value a", a);
            emit log_named_uint("  Value b", b);
            fail();
        }
    }
    function assertLe(uint a, uint b, string memory err) internal {
        if (a > b) {
            emit log_named_string("Error", err);
            assertLe(a, b);
        }
    }
    function assertLe(int a, int b) internal {
        if (a > b) {
            emit log("Error: a <= b not satisfied [int]");
            emit log_named_int("  Value a", a);
            emit log_named_int("  Value b", b);
            fail();
        }
    }
    function assertLe(int a, int b, string memory err) internal {
        if (a > b) {
            emit log_named_string("Error", err);
            assertLe(a, b);
        }
    }
    function assertLeDecimal(int a, int b, uint decimals) internal {
        if (a > b) {
            emit log("Error: a <= b not satisfied [decimal int]");
            emit log_named_decimal_int("  Value a", a, decimals);
            emit log_named_decimal_int("  Value b", b, decimals);
            fail();
        }
    }
    function assertLeDecimal(int a, int b, uint decimals, string memory err) internal {
        if (a > b) {
            emit log_named_string("Error", err);
            assertLeDecimal(a, b, decimals);
        }
    }
    function assertLeDecimal(uint a, uint b, uint decimals) internal {
        if (a > b) {
            emit log("Error: a <= b not satisfied [decimal uint]");
            emit log_named_decimal_uint("  Value a", a, decimals);
            emit log_named_decimal_uint("  Value b", b, decimals);
            fail();
        }
    }
    function assertLeDecimal(uint a, uint b, uint decimals, string memory err) internal {
        if (a > b) {
            emit log_named_string("Error", err);
            assertGeDecimal(a, b, decimals);
        }
    }

    function assertEq(string memory a, string memory b) internal {
        if (keccak256(abi.encodePacked(a)) != keccak256(abi.encodePacked(b))) {
            emit log("Error: a == b not satisfied [string]");
            emit log_named_string("  Value a", a);
            emit log_named_string("  Value b", b);
            fail();
        }
    }
    function assertEq(string memory a, string memory b, string memory err) internal {
        if (keccak256(abi.encodePacked(a)) != keccak256(abi.encodePacked(b))) {
            emit log_named_string("Error", err);
            assertEq(a, b);
        }
    }

    function checkEq0(bytes memory a, bytes memory b) internal pure returns (bool ok) {
        ok = true;
        if (a.length == b.length) {
            for (uint i = 0; i < a.length; i++) {
                if (a[i] != b[i]) {
                    ok = false;
                }
            }
        } else {
            ok = false;
        }
    }
    function assertEq0(bytes memory a, bytes memory b) internal {
        if (!checkEq0(a, b)) {
            emit log("Error: a == b not satisfied [bytes]");
            emit log_named_bytes("  Expected", a);
            emit log_named_bytes("    Actual", b);
            fail();
        }
    }
    function assertEq0(bytes memory a, bytes memory b, string memory err) internal {
        if (!checkEq0(a, b)) {
            emit log_named_string("Error", err);
            assertEq0(a, b);
        }
    }
}

// src/Utils.sol

library Utils {

    function codeSize(address _addr) internal view returns (uint256 size) {
    assembly {
      size := extcodesize(_addr)
    }
  }

  function codeAt(
    address _addr,
    uint256 _start,
    uint256 _end
  ) internal view returns (bytes memory oCode) {
    uint256 csize = codeSize(_addr);
    if (csize == 0) return bytes("");

    if (_start > csize) return bytes("");
    // if (_end < _start) revert InvalidCodeAtRange(csize, _start, _end);

    unchecked {
      uint256 reqSize = _end - _start;
      uint256 maxSize = csize - _start;

      uint256 size = maxSize < reqSize ? maxSize : reqSize;

      assembly {
        // allocate output byte array - this could also be done without assembly
        // by using o_code = new bytes(size)
        oCode := mload(0x40)
        // new "memory end" including padding
        mstore(
          0x40,
          add(oCode, and(add(add(size, add(_start, 0x20)), 0x1f), not(0x1f)))
        )
        // store length in memory
        mstore(oCode, size)
        // actually retrieve the code, this needs assembly
        extcodecopy(_addr, add(oCode, 0x20), _start, size)
      }
    }
  }

  function codeAtLen(
    address _addr,
    uint256 _start,
    uint256 _len
  ) internal view returns (bytes memory oCode) {
    
    unchecked {
      assembly {
        // allocate output byte array - this could also be done without assembly
        // by using o_code = new bytes(size)
        oCode := mload(0x40)
        // new "memory end" including padding
        mstore(
          0x40,
          add(oCode, and(add(add(_len, add(_start, 0x20)), 0x1f), not(0x1f)))
        )
        // store length in memory
        mstore(oCode, _len)
        // actually retrieve the code, this needs assembly
        extcodecopy(_addr, add(oCode, 0x20), _start, _len)
      }
    }
  }
}

// src/ClonesWithCallData.sol

contract ClonesWithCallData is DSTest {
 
  function cloneWithCallDataProvision(address implementation, bytes memory data)
    internal
    returns (address instance)
  {
    uint256 extraLength = data.length + 2; // +2 bytes for telling how much data there is appended to the call
    uint256 creationSize = 0x43 + extraLength ;
    uint256 runSize = creationSize - 11;
    uint256 dataPtr;
    uint256 ptr;
    // solhint-disable-next-line no-inline-assembly
    assembly {
      ptr := mload(0x40)

      // -------------------------------------------------------------------------------------------------------------
      // CREATION (11 bytes)
      // -------------------------------------------------------------------------------------------------------------

      // 3d          | RETURNDATASIZE        | 0                       | –
      // 61 runtime  | PUSH2 runtime (r)     | r 0                     | –
      mstore(
        ptr,
        0x3d61000000000000000000000000000000000000000000000000000000000000
      )
      mstore(add(ptr, 0x02), shl(240, runSize)) // size of the contract running bytecode (16 bits)

      // creation size = 0b
      // 80          | DUP1                  | r r 0                   | –
      // 60 creation | PUSH1 creation (c)    | c r r 0                 | –
      // 3d          | RETURNDATASIZE        | 0 c r r 0               | –
      // 39          | CODECOPY              | r 0                     | [0-2d]: runtime code
      // 81          | DUP2                  | 0 c  0                  | [0-2d]: runtime code
      // f3          | RETURN                | 0                       | [0-2d]: runtime code
      mstore(
        add(ptr, 0x04),
        0x80600b3d3981f300000000000000000000000000000000000000000000000000
      )

      // -------------------------------------------------------------------------------------------------------------
      // RUNTIME
      // -------------------------------------------------------------------------------------------------------------

      // 36          | CALLDATASIZE          | cds                     | –
      // 3d          | RETURNDATASIZE        | 0 cds                   | –
      // 3d          | RETURNDATASIZE        | 0 0 cds                 | –
      // 37          | CALLDATACOPY          | –                       | [0, cds] = calldata
      // 61          | PUSH2 extra           | extra                   | [0, cds] = calldata
       mstore(
        add(ptr, 0x0b),
        0x363d3d3761000000000000000000000000000000000000000000000000000000
      )
      mstore(
        add(ptr, 0x10),
        shl(240, extraLength)
      )

      // 60 0x38     | PUSH1 0x38            | 0x38 extra              | [0, cds] = calldata // 0x38 (56) is runtime size - data
      // 36          | CALLDATASIZE          | cds 0x38 extra          | [0, cds] = calldata
      // 39          | CODECOPY              | _                       | [0, cds] = calldata
      // 3d          | RETURNDATASIZE        | 0                       | [0, cds] = calldata
      // 3d          | RETURNDATASIZE        | 0 0                     | [0, cds] = calldata
      // 3d          | RETURNDATASIZE        | 0 0 0                   | [0, cds] = calldata
      // 36          | CALLDATASIZE          | cds 0 0 0               | [0, cds] = calldata
      // 61 extra    | PUSH2 extra           | extra cds 0 0 0         | [0, cds] = calldata
      mstore(
        add(ptr, 0x12),
        0x603836393d3d3d36610000000000000000000000000000000000000000000000
      )
       mstore(
        add(ptr, 0x1b),
        shl(240, extraLength)
      )

      // 01          | ADD                   | cds+extra 0 0 0         | [0, cds] = calldata
      // 3d          | RETURNDATASIZE        | 0 cds 0 0 0             | [0, cds] = calldata
      // 73 addr     | PUSH20 0x123…         | addr 0 cds 0 0 0        | [0, cds] = calldata
      mstore(add(ptr, 0x1d), 0x013d730000000000000000000000000000000000000000000000000000000000)
      mstore(add(ptr, 0x20), shl(0x60, implementation))

      // 5a          | GAS                   | gas addr 0 cds 0 0 0    | [0, cds] = calldata
      // f4          | DELEGATECALL          | success 0                | [0, cds] = calldata
      // 3d          | RETURNDATASIZE        | rds success 0           | [0, cds] = calldata
      // 82          | DUP3                  | 0 rds success 0         | [0, cds] = calldata
      // 80          | DUP1                  | 0 0 rds success 0       | [0, cds] = calldata
      // 3e          | RETURNDATACOPY        | success 0               | [0, rds] = return data (there might be some irrelevant leftovers in memory [rds, cds] when rds < cds)
      // 90          | SWAP1                 | 0 success               | [0, rds] = return data
      // 3d          | RETURNDATASIZE        | rds 0 success           | [0, rds] = return data
      // 91          | SWAP2                 | success 0 rds           | [0, rds] = return data
      // 60 0x36     | PUSH1 0x36            | 0x36 sucess 0 rds       | [0, rds] = return data
      // 57          | JUMPI                 | 0 rds                   | [0, rds] = return data
      // fd          | REVERT                | –                       | [0, rds] = return data
      // 5b          | JUMPDEST              | 0 rds                   | [0, rds] = return data
      // f3          | RETURN                | –                       | [0, rds] = return data

      mstore(
        add(ptr, 0x34),
        0x5af43d82803e903d91603657fd5bf30000000000000000000000000000000000
      )
    }

    // -------------------------------------------------------------------------------------------------------------
    // APPENDED DATA (Accessible from extcodecopy)
    // (but also send as appended data to the delegatecall)
    // -------------------------------------------------------------------------------------------------------------

    extraLength -= 2;
    uint256 counter = extraLength;
    uint256 copyPtr = ptr + 0x43;
    // solhint-disable-next-line no-inline-assembly
    assembly {
      dataPtr := add(data, 32)
    }
    for (; counter >= 32; counter -= 32) {
      // solhint-disable-next-line no-inline-assembly
      assembly {
        mstore(copyPtr, mload(dataPtr))
      }
      copyPtr += 32;
      dataPtr += 32;
    }
    uint256 mask = ~(256**(32 - counter) - 1);
    // solhint-disable-next-line no-inline-assembly
    assembly {
      mstore(copyPtr, and(mload(dataPtr), mask))
    }
    copyPtr += (32 - counter);
     // solhint-disable-next-line no-inline-assembly
    assembly {
      mstore(copyPtr, shl(240, extraLength))
    }
    // solhint-disable-next-line no-inline-assembly
    assembly {
      instance := create(0, ptr, creationSize)
    }
    require(instance != address(0), "create failed");
  }

}

// src/ClonesWithImmutableArgs.sol

contract ClonesWithImmutableArgs is DSTest {
  
  function clone(address implementation, bytes memory data)
    internal
    returns (address instance)
  {
    uint256 extraLength = data.length;
    uint256 creationSize = 0x38 + extraLength;
    uint256 runSize = creationSize - 11;
    uint256 dataPtr;
    uint256 ptr;
    // solhint-disable-next-line no-inline-assembly
    assembly {
      ptr := mload(0x40)

      // -------------------------------------------------------------------------------------------------------------
      // CREATION (11 bytes)
      // -------------------------------------------------------------------------------------------------------------

      // 3d          | RETURNDATASIZE        | 0                       | –
      // 61 runtime  | PUSH2 runtime (r)     | r 0                     | –
      mstore(
        ptr,
        0x3d61000000000000000000000000000000000000000000000000000000000000
      )
      mstore(add(ptr, 0x02), shl(240, runSize)) // size of the contract running bytecode (16 bits)

      // creation size = 0b
      // 80          | DUP1                  | r r 0                   | –
      // 60 creation | PUSH1 creation (c)    | c r r 0                 | –
      // 3d          | RETURNDATASIZE        | 0 c r r 0               | –
      // 39          | CODECOPY              | r 0                     | [0-2d]: runtime code
      // 81          | DUP2                  | 0 c  0                  | [0-2d]: runtime code
      // f3          | RETURN                | 0                       | [0-2d]: runtime code
      mstore(
        add(ptr, 0x04),
        0x80600b3d3981f300000000000000000000000000000000000000000000000000
      )

      // -------------------------------------------------------------------------------------------------------------
      // RUNTIME
      // -------------------------------------------------------------------------------------------------------------

      // 36          | CALLDATASIZE          | cds                     | –
      // 3d          | RETURNDATASIZE        | 0 cds                   | –
      // 3d          | RETURNDATASIZE        | 0 0 cds                 | –
      // 37          | CALLDATACOPY          | –                       | [0, cds] = calldata
      // 3d          | RETURNDATASIZE        | 0                       | [0, cds] = calldata
      // 3d          | RETURNDATASIZE        | 0 0                     | [0, cds] = calldata
      // 3d          | RETURNDATASIZE        | 0 0 0                   | [0, cds] = calldata
      // 36          | CALLDATASIZE          | cds 0 0 0               | [0, cds] = calldata
      // 3d          | RETURNDATASIZE        | 0 cds 0 0 0             | [0, cds] = calldata
      // 73 addr     | PUSH20 0x123…         | addr 0 cds 0 0 0        | [0, cds] = calldata
      mstore(
        add(ptr, 0x0b),
        0x363d3d373d3d3d363d7300000000000000000000000000000000000000000000
      )
      mstore(add(ptr, 0x15), shl(0x60, implementation))

      // 5a          | GAS                   | gas addr 0 cds 0 0 0    | [0, cds] = calldata
      // f4          | DELEGATECALL          | success 0                | [0, cds] = calldata
      // 3d          | RETURNDATASIZE        | rds success 0           | [0, cds] = calldata
      // 82          | DUP3                  | 0 rds success 0         | [0, cds] = calldata
      // 80          | DUP1                  | 0 0 rds success 0       | [0, cds] = calldata
      // 3e          | RETURNDATACOPY        | success 0               | [0, rds] = return data (there might be some irrelevant leftovers in memory [rds, cds] when rds < cds)
      // 90          | SWAP1                 | 0 success               | [0, rds] = return data
      // 3d          | RETURNDATASIZE        | rds 0 success           | [0, rds] = return data
      // 91          | SWAP2                 | success 0 rds           | [0, rds] = return data
      // 60 dest     | PUSH1 dest            | dest sucess 0 rds       | [0, rds] = return data
      // 57          | JUMPI                 | 0 rds                   | [0, rds] = return data
      // fd          | REVERT                | –                       | [0, rds] = return data
      // 5b          | JUMPDEST              | 0 rds                   | [0, rds] = return data
      // f3          | RETURN                | –                       | [0, rds] = return data

      mstore(
        add(ptr, 0x29),
        0x5af43d82803e903d91602b57fd5bf30000000000000000000000000000000000
      )
    }

    // -------------------------------------------------------------------------------------------------------------
    // APPENDED DATA (Accessible from extcodecopy)
    // -------------------------------------------------------------------------------------------------------------

    uint256 copyPtr = ptr + 0x38;
    // solhint-disable-next-line no-inline-assembly
    assembly {
      dataPtr := add(data, 32)
    }
    for (; extraLength >= 32; extraLength -= 32) {
      // solhint-disable-next-line no-inline-assembly
      assembly {
        mstore(copyPtr, mload(dataPtr))
      }
      copyPtr += 32;
      dataPtr += 32;
    }
    uint256 mask = ~(256**(32 - extraLength) - 1);
    // solhint-disable-next-line no-inline-assembly
    assembly {
      mstore(copyPtr, and(mload(dataPtr), mask))
    }
    // solhint-disable-next-line no-inline-assembly
    assembly {
      instance := create(0, ptr, creationSize)
    }
    require(instance != address(0), "create failed");
  }

}

// src/Template.sol

contract Template is ClonesWithImmutableArgs, ClonesWithCallData {

    event Cloned(address addr);

    function clone1(bytes calldata data) external returns (Template clonedGreeter) {
        clonedGreeter = Template(ClonesWithImmutableArgs.clone(address(this), data));
        emit Cloned(address(clonedGreeter));
    }

    function clone2(bytes calldata data) external returns (Template clonedGreeter) {
        clonedGreeter = Template(ClonesWithCallData.cloneWithCallDataProvision(address(this), data));
        emit Cloned(address(clonedGreeter));
    }
 }
 