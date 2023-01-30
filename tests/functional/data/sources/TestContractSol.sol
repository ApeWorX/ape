// SPDX-License-Identifier: MIT
pragma solidity ^0.8.2;

contract TestContractSol {
    address public owner;
    uint256 public myNumber;
    uint256 public prevNumber;
    address public theAddress;
    mapping(address => uint256) public balances;
    uint256[][3] dynArray;
    uint256[][3][][5] mixedArray;

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

    modifier onlyOwner() {
        require(msg.sender == owner, "!authorized");
        _;
    }

    constructor(uint256 num) {
        myNumber = num;
        owner = msg.sender;

        dynArray[0] = [uint(0)];
        dynArray[1] = [uint(0), 1];
        dynArray[2] = [uint(0), 1, 2];

        mixedArray[0].push(dynArray);
        mixedArray[1].push(dynArray);
        mixedArray[1].push(dynArray);
    }

    function fooAndBar() public {
        emit FooHappened(0);
        emit BarHappened(1);
    }

    function setNumber(uint256 num) public onlyOwner {
        require(num != 5);
        prevNumber = myNumber;
        myNumber = num;
        emit NumberChange(blockhash(block.number - 1), prevNumber, "Dynamic", num, "Dynamic");
    }

    function setNumber(uint256 num, address _address) public onlyOwner {
        // Purposely have same method name as above for testing purposes.
        require(num != 5);
        prevNumber = myNumber;
        myNumber = num;
        theAddress = _address;
        emit NumberChange(blockhash(block.number - 1), prevNumber, "Dynamic", num, "Dynamic");
    }

    function setAddress(address _address) public {
        theAddress = _address;
        emit AddressChange(_address);
    }

    function setBalance(address _address, uint256 bal) public {
        balances[_address] += bal;
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

    function getEmptyDynArrayOfStructs() public pure returns(MyStruct[] memory) {
        MyStruct[] memory _my_structs;
        return _my_structs;
    }

    function getEmptyTupleOfDynArrayStructs() public pure returns(MyStruct[] memory, MyStruct[] memory) {
        MyStruct[] memory _my_structs_0;
        MyStruct[] memory _my_structs_1;
        return (_my_structs_0, _my_structs_1);
    }

    function getEmptyTupleOfArrayOfStructsAndDynArrayOfStructs() public pure returns(MyStruct[2] memory, MyStruct[] memory) {
        MyStruct[2] memory _my_structs_0;
        MyStruct[] memory _my_structs_1;
        return (_my_structs_0, _my_structs_1);
    }

    function getEmptyTupleOfIntAndDynArray() public pure returns(uint256[] memory, MyStruct[] memory) {
        uint256[] memory _integers;
        MyStruct[] memory _structs;
        return (_integers, _structs);
    }

    function getStructWithArray() public view returns(WithArray memory) {
        MyStruct[2] memory arr = [getStruct(), getStruct()];
        return WithArray(1, arr, 2);
    }

    function getEmptyArray() public pure returns(uint256[] memory) {
        uint256[] memory data;
        return data;
    }

    function getSingleItemArray() public pure returns(uint256[1] memory) {
        uint256[1] memory data = [uint256(1)];
        return data;
    }

    function getFilledArray() public pure returns(uint256[3] memory) {
        uint256[3] memory data = [uint256(1), uint256(2), uint256(3)];
        return data;
    }

    function getAddressArray() public view returns(address[2] memory) {
        address[2] memory data = [msg.sender, msg.sender];
        return data;
    }

    function getDynamicStructArray() public view returns(NestedStruct1[] memory) {
        NestedStruct1[] memory data = new NestedStruct1[](2);
        data[0] = NestedStruct1(getStruct(), 1);
        data[1] = NestedStruct1(getStruct(), 2);
        return data;
    }

    function getStaticStructArray() public view returns(NestedStruct2[2] memory) {
      NestedStruct2[2] memory data = [NestedStruct2(1, getStruct()), NestedStruct2(2, getStruct())];
      return data;
    }

    function getArrayWithBiggerSize() public pure returns(uint256[20] memory) {
        uint256[20] memory data;
        return data;
    }

    function getTupleOfArrays() public pure returns(uint256[20] memory, uint256[20] memory) {
        uint256[20] memory data0;
        uint256[20] memory data1;
        return (data0, data1);
    }

    function getNamedSingleItem() public pure returns(uint256 foo) {
        return 123;
    }

    function getTupleAllNamed() public pure returns(uint256 foo, uint256 bar) {
        return (123, 321);
    }

    function getUnnamedTuple() public pure returns(uint256, uint256) {
        return (0, 0);
    }

    function getPartiallyNamedTuple() public pure returns(uint256 foo, uint256) {
        return (123, 321);
    }

    function getTupleOfAddressArray() public view returns(address[20] memory, int128[20] memory) {
        address[20] memory addresses;
        addresses[0] = msg.sender;
        int128[20] memory data;
        return (addresses, data);
    }

    function getNestedArrayFixedFixed() public pure returns(uint256[2][3] memory) {
        uint[2][3] memory arr = [[uint(1),2], [uint(3), 4], [uint(5), 6]];
        return arr;
    }

    function getNestedArrayDynamicFixed() public pure returns(uint256[2][] memory) {
        uint[2][] memory arr = new uint[2][](3);
        arr[0] = [uint(1), 2];
        arr[1] = [uint(3), 4];
        arr[2] = [uint(5), 6];
        return arr;
    }

    function getNestedArrayFixedDynamic() public view returns(uint256[][3] memory) {
        return dynArray;
    }

    function getNestedArrayMixedDynamic() public view returns(uint256[][3][][5] memory) {
        return mixedArray;
    }

    function getNestedAddressArray() public view returns(address[3][] memory) {
        address[3][] memory arr = new address[3][](2);
        arr[0] = [msg.sender, msg.sender, msg.sender];
        return arr;
    }

    function functionWithUniqueAmountOfArguments(
        uint256 a0,
        uint256 a1,
        uint256 a2,
        uint256 a3,
        uint256 a4,
        uint256 a5,
        uint256 a6,
        uint256 a7,
        uint256 a8,
        uint256 a9
    ) public view {

    }

    function setStruct(MyStruct memory _my_struct) public pure {

    }

    function setStructArray(MyStruct[2] memory _my_struct_array) public pure {

    }
}
