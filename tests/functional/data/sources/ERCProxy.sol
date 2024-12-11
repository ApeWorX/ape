pragma solidity ^0.4.18;

// Ref: https://eips.ethereum.org/EIPS/eip-897

contract ERCProxy {
  address internal target;

  constructor(address _target) {
    target = _target;
  }


  function implementation() public view returns (address) {
    return target;
  }

  function proxyType() public pure returns (uint256 proxyTypeId){
    return 1;
  }
}
