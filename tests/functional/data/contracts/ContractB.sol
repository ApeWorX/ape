// SPDX-License-Identifier: MIT
pragma solidity ^0.8.4;

import { Hero, ContractC } from "./ContractC.sol";


contract ContractB {

    ContractC public contractC;
    mapping(address => uint256) public bandPractice;
    mapping(address => string) public pumpkin;
    string public concatres = "";
    string public sharedString = "";
    address public sharedAddress = 0xF2Df0b975c0C9eFa2f8CA0491C2d1685104d2488;
    string public symbol = "SYMBOL";
    address[] visitors;

    event OneOfMany(address indexed addr);

    constructor(ContractC addr) {
        contractC = addr;
    }

    function oneOfMany() public {
        emit OneOfMany(msg.sender);
    }

    function setSharedString(string memory value) public {
        sharedString = value;
    }

    function setSharedAddress(address value) public {
        sharedAddress = value;
    }

    function supercluster(uint256 x) public returns(uint256[3][4] memory) {
        uint256[3] memory star0 = [uint256(23523523235235), uint256(11111111111), x];
        uint256[3] memory star1 = [uint256(345345347789999991), uint256(99999998888882), uint256(345457847457457458457457457)];
        uint256[3] memory star2 = [x, uint256(92222229999998888882), uint256(3454)];
        uint256[3] memory star3 = [uint256(111145345347789999991), uint256(333399998888882), uint256(234545457847457457458457457457)];
        visitors.push(msg.sender);
        return [star0, star1, star2, star3];
    }

    function methodB1(string memory lolol, uint dynamo) public {
        pumpkin[msg.sender] = lolol;

        contractC.getSomeList();
        contractC.methodC1("simpler", dynamo, msg.sender);
        bandPractice[msg.sender] = bandPractice[msg.sender] + dynamo;
    }

    function callMe(address blue) public pure returns(address) {
        return blue;
    }

    function methodB2(address trombone) public payable {
        (string memory os,,) = contractC.paperwork(msg.sender);
        contractC.methodC1(os, msg.value, address(contractC));
        bandPractice[trombone] = msg.value;
        contractC.methodC2();
        contractC.methodC2();
    }

    function alwaysFail(uint256 pointlessArgument) public {
        if (true) {
            revert("I always fail :)");
        }
        bandPractice[msg.sender] = 912412512412341241254;
        bandPractice[msg.sender] = pointlessArgument;
    }
}
