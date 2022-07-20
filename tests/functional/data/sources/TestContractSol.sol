// SPDX-License-Identifier: MIT
pragma solidity ^0.8.2;

contract TestContractSol {
    address public owner;
    uint256 public myNumber;
    uint256 public prevNumber;
    address public theAddress;

    event NumberChange(
        bytes32 b,
        uint256 prevNum,
        string dynData,
        uint256 indexed newNum,
        string indexed dynIndexed
    );

    event AddressChange(
        address indexed newAddress
    );

    event FooHappened(
        uint256 indexed foo
    );

    event BarHappened(
        uint256 indexed bar
    );

    struct MyStruct {
        address a;
        bytes32 b;
    }

    struct NestedStruct1 {
        MyStruct t;
        uint256 foo;
    }

    struct NestedStruct2 {
        uint256 foo;
        MyStruct t;
    }

    struct WithArray {
        uint256 foo;
        MyStruct[2] arr;
        uint256 bar;
    }

    constructor() {
        owner = msg.sender;
    }

    function fooAndBar() public {
        emit FooHappened(0);
        emit BarHappened(1);
    }

    function setNumber(uint256 num) public {
        require(msg.sender == owner, "!authorized");
        require(num != 5);
        prevNumber = myNumber;
        myNumber = num;
        emit NumberChange(blockhash(block.number - 1), prevNumber, "Dynamic", num, "Dynamic");
    }

    function setAddress(address _address) public {
        theAddress = _address;
        emit AddressChange(_address);
    }

    function getStruct() public view returns(MyStruct memory) {
        return MyStruct(msg.sender, blockhash(block.number - 1));
    }

    function getNestedStruct1() public view returns(NestedStruct1 memory) {
        return NestedStruct1(getStruct(), 1);
    }

    function getNestedStruct2() public view returns(NestedStruct2 memory) {
        return NestedStruct2(2, getStruct());
    }

    function getNestedStructWithTuple1() public view returns(NestedStruct1 memory, uint256) {
        return (NestedStruct1(getStruct(), 1), 1);
    }

    function getNestedStructWithTuple2() public view returns(uint256, NestedStruct2 memory) {
        return (2, NestedStruct2(2, getStruct()));
    }

    function getStructWithArray() public view returns(WithArray memory) {
        MyStruct[2] memory arr = [getStruct(), getStruct()];
        return WithArray(1, arr, 2);
    }

    function getEmptyList() public pure returns(uint256[] memory) {
        uint256[] memory data;
        return data;
    }

    function getSingleItemList() public pure returns(uint256[1] memory) {
        uint256[1] memory data = [uint256(1)];
        return data;
    }

    function getFilledList() public pure returns(uint256[3] memory) {
        uint256[3] memory data = [uint256(1), uint256(2), uint256(3)];
        return data;
    }

    function getAddressList() public view returns(address[2] memory) {
        address[2] memory data = [msg.sender, msg.sender];
        return data;
    }

    function getDynamicStructList() public view returns(NestedStruct1[] memory) {
        NestedStruct1[] memory data = new NestedStruct1[](2);
        data[0] = NestedStruct1(getStruct(), 1);
        data[1] = NestedStruct1(getStruct(), 2);
        return data;
    }

    function getStaticStructList() public view returns(NestedStruct2[2] memory) {
      NestedStruct2[2] memory data = [NestedStruct2(1, getStruct()), NestedStruct2(2, getStruct())];
      return data;
    }

    function getNamedSingleItem() public pure returns(uint256 foo) {
        return 123;
    }

    function getTupleAllNamed() public pure returns(uint256 foo, uint256 bar) {
        return (123, 321);
    }

    function getPartiallyNamedTuple() public pure returns(uint256 foo, uint256) {
        return (123, 321);
    }
}
