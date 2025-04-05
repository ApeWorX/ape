// SPDX-License-Identifier: MIT
pragma solidity ^0.8.2;

import "./ContractB.sol";

contract ContractA {

    event Bobber(
        address indexed sinker,
        uint256 indexed hook
    );

    event OneOfMany(address indexed addr);

    ContractB public contractB;
    ContractC public contractC;
    mapping(address => uint256) public runTheJules;
    string public sharedString = "";
    address payable owner = payable(0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C);

    constructor(ContractB addrb, ContractC addrc) {
        contractB = addrb;
        contractC = addrc;
    }

    function gonefishin() public {
        emit Bobber(address(msg.sender), 4);
        emit Bobber(address(contractB), 4);
        emit Bobber(address(contractB), 4);
    }

    function callCallMe() public payable returns(uint256) {
        (bool success,) = address(contractB).call(abi.encodeWithSignature("callMe(address)", msg.sender));
        require(success);
        return 3;
    }

    function callDelegateCall() public {
        (bool success,) = address(contractB).delegatecall(abi.encodeWithSignature("setSharedString(string)", "testy"));
        require(success);
    }

    function callDelegateCall2() public {
        (bool success,) = address(contractB).delegatecall(abi.encodeWithSignature("setSharedAddress(address)", msg.sender));
        require(success);
    }

    function methodWithoutArguments() public payable returns(bytes memory) {
        uint256[3][4] memory myPlan = contractB.supercluster(234444);
        contractB.methodB1("ice-cream", myPlan[1][2]);

        (bool success, bytes memory res) = address(contractB).call(abi.encodeWithSignature("callMe(address)", msg.sender));
        require(success);

        contractB.methodB2(msg.sender);
        runTheJules[address(contractC)] = contractC.addressToValue(msg.sender);

        uint256 val = contractB.bandPractice(msg.sender);
        contractB.methodB1("lemondrop", val);
        contractB.methodB1("snitches_get_stiches", 111);

        return res;
    }

    function methodWithSingleArgument(uint256 rtj) public payable returns(bool) {
        runTheJules[msg.sender] = rtj;
        contractB.methodB1("craigslist", 5);
        contractB.methodB2(msg.sender);
        contractB.methodB2(msg.sender);
        uint256 val = contractB.bandPractice(msg.sender);
        runTheJules[msg.sender] += val;
        return true;
    }

    function goodbye() public {
        selfdestruct(owner);
    }

    function emitLogWithSameInterfaceFromMultipleContracts() public {
        contractB.oneOfMany();
        contractC.oneOfMany();
        emit OneOfMany(msg.sender);
    }

    receive() external payable {}
}
