LOCAL_TRACE = """
ContractA.methodWithoutArguments() -> 0x00..7a9c [469604 gas]
├── CALL: SYMBOL.<0x045856de>  [461506 gas]
├── SYMBOL.methodB1(lolol="ice-cream", dynamo=345457847457457458457457457)
│   [402067 gas]
│   ├── ContractC.getSomeList() -> [
│   │     3425311345134513461345134534531452345,
│   │     111344445534535353,
│   │     993453434534534534534977788884443333
│   │   ] [370103 gas]
│   └── ContractC.methodC1(
│         windows95="simpler",
│         jamaica=345457847457457458457457457,
│         cardinal=0xF2Df0b975c0C9eFa2f8CA0491C2d1685104d2488
│       ) [363869 gas]
├── SYMBOL.callMe(blue=0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C) ->
│   0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C [233432 gas]
├── SYMBOL.methodB2(trombone=0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C) [231951
│   gas]
│   ├── ContractC.paperwork(0xF2Df0b975c0C9eFa2f8CA0491C2d1685104d2488) -> (
│   │     os="simpler",
│   │     country=345457847457457458457457457,
│   │     wings=0xF2Df0b975c0C9eFa2f8CA0491C2d1685104d2488
│   │   ) [227360 gas]
│   ├── ContractC.methodC1(
│   │     windows95="simpler",
│   │     jamaica=0,
│   │     cardinal=0x274b028b03A250cA03644E6c578D81f019eE1323
│   │   ) [222263 gas]
│   ├── ContractC.methodC2() [147236 gas]
│   └── ContractC.methodC2() [122016 gas]
├── ContractC.addressToValue(0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C) -> 0
│   [100305 gas]
├── SYMBOL.bandPractice(0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C) -> 0 [94270
│   gas]
├── SYMBOL.methodB1(lolol="lemondrop", dynamo=0) [92321 gas]
│   ├── ContractC.getSomeList() -> [
│   │     3425311345134513461345134534531452345,
│   │     111344445534535353,
│   │     993453434534534534534977788884443333
│   │   ] [86501 gas]
│   └── ContractC.methodC1(
│         windows95="simpler",
│         jamaica=0,
│         cardinal=0xF2Df0b975c0C9eFa2f8CA0491C2d1685104d2488
│       ) [82729 gas]
└── SYMBOL.methodB1(lolol="snitches_get_stiches", dynamo=111) [55252 gas]
    ├── ContractC.getSomeList() -> [
    │     3425311345134513461345134534531452345,
    │     111344445534535353,
    │     993453434534534534534977788884443333
    │   ] [52079 gas]
    └── ContractC.methodC1(
          windows95="simpler",
          jamaica=111,
          cardinal=0xF2Df0b975c0C9eFa2f8CA0491C2d1685104d2488
        ) [48306 gas]
"""
MAINNET_TRACE = """
DSProxy.execute(_target=CompoundFlashLoanTaker, _data=0xf7..0000) -> '' [1070997 gas] [0.02016 value]
└── (delegate) CompoundFlashLoanTaker.boostWithLoan(
      _exData=[
        TetherToken,
        0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE,
        22000000000,
        0,
        2004750000000000000000000000,
        0x3Ba0319533C578527aE69BF7fA2D289F20B9B55c,
        Exchange,
        0xa6..ac67,
        2025000000000000000000000000
      ],
      _cAddresses=['CEther', 'CErc20Delegator'],
      _gasCost=0
    ) [1041213 gas] [0.02016 value]
    ├── GasToken2.balanceOf(owner=DSProxy) -> 0 [1303 gas]
    ├── STATICCALL: Unitroller.<0x5ec88c79>  [118577 gas]
    │   └── (delegate) Comptroller.getAccountLiquidity(account=DSProxy) -> [0, 100216217422739835644076, 0] [116582 gas]
    │       ├── CEther.getAccountSnapshot(account=DSProxy) -> [
    │       │     0,
    │       │     3588278641674,
    │       │     0,
    │       │     200289710046448107458251737
    │       │   ] [7747 gas]
    │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CEther) -> 493495000000000000000 [2843 gas]
    │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207745199249144216861107666] [20072 gas]
    │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..65d2 [16646 gas]
    │       │       └── (delegate) CDaiDelegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207745199249144216861107666] [13461 gas]
    │       │           ├── STATICCALL: 0x197E90f9FAD81970bA7976f33CbD77088E5D7cf7.<0x0bebac86>  [1215 gas]
    │       │           └── STATICCALL: 0x197E90f9FAD81970bA7976f33CbD77088E5D7cf7.<0xc92aecc4>  [1093 gas]
    │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1006638000000000000 [2931 gas]
    │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [
    │       │     0,
    │       │     1997736502878,
    │       │     0,
    │       │     201101221772832467767996110
    │       │   ] [16641 gas]
    │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..2ece [13215 gas]
    │       │       └── (delegate) CCompLikeDelegate.getAccountSnapshot(account=DSProxy) -> [
    │       │             0,
    │       │             1997736502878,
    │       │             0,
    │       │             201101221772832467767996110
    │       │           ] [10030 gas]
    │       │           └── STATICCALL: 0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984.<0x70a08231>  [1497 gas]
    │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 3722050000000000000 [3635 gas]
    │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 166685375217, 203684337093459] [19027 gas]
    │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..0b53 [16924 gas]
    │       │       └── (delegate) CErc20Delegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 166685375217, 203684337093459] [13739 gas]
    │       │           └── TetherToken.balanceOf(who=CErc20Delegator) -> 9409870971804 [2431 gas]
    │       └── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1000000000000000000000000000000 [2299 gas]
    ├── STATICCALL: Unitroller.<0x7dc0d1d0>  [3073 gas]
    │   └── (delegate) Comptroller.oracle() -> UniswapAnchoredView [1105 gas]
    ├── CErc20Delegator.accrueInterest() -> 0 [42845 gas]
    │   └── (delegate) CErc20Delegate.accrueInterest() -> 0 [40830 gas]
    │       ├── TetherToken.balanceOf(who=CErc20Delegator) -> 9409870971804 [2431 gas]
    │       └── JumpRateModelV2.getBorrowRate(
    │             cash=9409870971804,
    │             borrows=31969908998585,
    │             reserves=116282802900
    │           ) -> 18425955753 [3858 gas]
    ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1000000000000000000000000000000 [2299 gas]
    ├── TetherToken.balanceOf(who=0x3dfd23A6c5E8BbcFc9581d2E864a68feb6a076d3) -> 7334120405865 [2431 gas]
    ├── CALL: Unitroller.<0xc2998238>  [7351 gas]
    │   └── (delegate) Comptroller.enterMarkets(cTokens=['CEther', 'CErc20Delegator']) -> [0, 0] [5335 gas]
    ├── DSProxy.owner() -> tx.origin [1247 gas]
    ├── STATICCALL: Unitroller.<0x5ec88c79>  [118577 gas]
    │   └── (delegate) Comptroller.getAccountLiquidity(account=DSProxy) -> [0, 100215845790739835644076, 0] [116582 gas]
    │       ├── CEther.getAccountSnapshot(account=DSProxy) -> [
    │       │     0,
    │       │     3588278641674,
    │       │     0,
    │       │     200289710046448107458251737
    │       │   ] [7747 gas]
    │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CEther) -> 493495000000000000000 [2843 gas]
    │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207745199249144216861107666] [20072 gas]
    │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..65d2 [16646 gas]
    │       │       └── (delegate) CDaiDelegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207745199249144216861107666] [13461 gas]
    │       │           ├── STATICCALL: 0x197E90f9FAD81970bA7976f33CbD77088E5D7cf7.<0x0bebac86>  [1215 gas]
    │       │           └── STATICCALL: 0x197E90f9FAD81970bA7976f33CbD77088E5D7cf7.<0xc92aecc4>  [1093 gas]
    │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1006638000000000000 [2931 gas]
    │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [
    │       │     0,
    │       │     1997736502878,
    │       │     0,
    │       │     201101221772832467767996110
    │       │   ] [16641 gas]
    │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..2ece [13215 gas]
    │       │       └── (delegate) CCompLikeDelegate.getAccountSnapshot(account=DSProxy) -> [
    │       │             0,
    │       │             1997736502878,
    │       │             0,
    │       │             201101221772832467767996110
    │       │           ] [10030 gas]
    │       │           └── STATICCALL: 0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984.<0x70a08231>  [1497 gas]
    │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 3722050000000000000 [3635 gas]
    │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 166685746849, 203684618567521] [19027 gas]
    │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..ff61 [16924 gas]
    │       │       └── (delegate) CErc20Delegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 166685746849, 203684618567521] [13739 gas]
    │       │           └── TetherToken.balanceOf(who=CErc20Delegator) -> 9409870971804 [2431 gas]
    │       └── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1000000000000000000000000000000 [2299 gas]
    ├── STATICCALL: Unitroller.<0x7dc0d1d0>  [3073 gas]
    │   └── (delegate) Comptroller.oracle() -> UniswapAnchoredView [1105 gas]
    ├── CErc20Delegator.accrueInterest() -> 0 [3195 gas]
    │   └── (delegate) CErc20Delegate.accrueInterest() -> 0 [1180 gas]
    ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1000000000000000000000000000000 [2299 gas]
    ├── CErc20Delegator.borrow(borrowAmount=22000000000) -> 0 [274012 gas]
    │   └── (delegate) CErc20Delegate.borrow(borrowAmount=22000000000) -> 0 [271908 gas]
    │       ├── CALL: Unitroller.<0xda3d454c>  [193142 gas]
    │       │   └── (delegate) Comptroller.borrowAllowed(
    │       │         cToken=CErc20Delegator,
    │       │         borrower=DSProxy,
    │       │         borrowAmount=22000000000
    │       │       ) -> 0 [191162 gas]
    │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1000000000000000000000000000000 [2299 gas]
    │       │       ├── CEther.getAccountSnapshot(account=DSProxy) -> [
    │       │       │     0,
    │       │       │     3588278641674,
    │       │       │     0,
    │       │       │     200289710046448107458251737
    │       │       │   ] [7747 gas]
    │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CEther) -> 493495000000000000000 [2843 gas]
    │       │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207745199249144216861107666] [20072 gas]
    │       │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..65d2 [16646 gas]
    │       │       │       └── (delegate) CDaiDelegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207745199249144216861107666] [13461 gas]
    │       │       │           ├── STATICCALL: 0x197E90f9FAD81970bA7976f33CbD77088E5D7cf7.<0x0bebac86>  [1215 gas]
    │       │       │           └── STATICCALL: 0x197E90f9FAD81970bA7976f33CbD77088E5D7cf7.<0xc92aecc4>  [1093 gas]
    │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1006638000000000000 [2931 gas]
    │       │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [
    │       │       │     0,
    │       │       │     1997736502878,
    │       │       │     0,
    │       │       │     201101221772832467767996110
    │       │       │   ] [16641 gas]
    │       │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..2ece [13215 gas]
    │       │       │       └── (delegate) CCompLikeDelegate.getAccountSnapshot(account=DSProxy) -> [
    │       │       │             0,
    │       │       │             1997736502878,
    │       │       │             0,
    │       │       │             201101221772832467767996110
    │       │       │           ] [10030 gas]
    │       │       │           └── STATICCALL: 0x1f9840a85d5aF5bf1D1762F925BDADdC4201F984.<0x70a08231>  [1497 gas]
    │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 3722050000000000000 [3635 gas]
    │       │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 166685746849, 203684618567521] [19027 gas]
    │       │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..ff61 [16924 gas]
    │       │       │       └── (delegate) CErc20Delegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 166685746849, 203684618567521] [13739 gas]
    │       │       │           └── TetherToken.balanceOf(who=CErc20Delegator) -> 9409870971804 [2431 gas]
    │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1000000000000000000000000000000 [2299 gas]
    │       │       ├── CErc20Delegator.borrowIndex() -> 1045063620842360840 [1087 gas]
    │       │       ├── CErc20Delegator.totalBorrows() -> 31969980276796 [1154 gas]
    │       │       ├── CErc20Delegator.borrowBalanceStored(account=DSProxy) -> 166685746849 [9329 gas]
    │       │       │   └── CErc20Delegator.delegateToImplementation(data=0x95..52dd) -> 0x00..a6a1 [7205 gas]
    │       │       │       └── (delegate) CErc20Delegate.borrowBalanceStored(account=DSProxy) -> 166685746849 [4248 gas]
    │       │       ├── Comp.balanceOf(account=Unitroller) -> 37814309293046111340279 [1488 gas]
    │       │       └── Comp.transfer(dst=DSProxy, rawAmount=454823446030875984) -> True [19090 gas]
    │       ├── TetherToken.balanceOf(who=CErc20Delegator) -> 9409870971804 [2431 gas]
    │       ├── TetherToken.transfer(_to=DSProxy, _value=22000000000) [34601 gas]
    │       └── CALL: Unitroller.<0x5c778605>  [2261 gas]
    │           └── (delegate) Comptroller.borrowVerify(
    │                 cToken=CErc20Delegator,
    │                 borrower=DSProxy,
    │                 borrowAmount=22000000000
    │               ) [354 gas]
    ├── CErc20Delegator.underlying() -> TetherToken [1148 gas]
    ├── BotRegistry.botList(tx.origin) -> False [1136 gas]
    ├── CErc20Delegator.underlying() -> TetherToken [1148 gas]
    ├── Discount.isCustomFeeSet(_user=tx.origin) -> False [1299 gas]
    ├── TetherToken.transfer(
    │     _to=0x322d58b9E75a6918f7e7849AEe0fF09369977e08,
    │     _value=55000000
    │   ) [15401 gas]
    ├── TetherToken.approve(_spender=ERC20Proxy, _value=0) [4160 gas]
    ├── TetherToken.approve(_spender=ERC20Proxy, _value=21945000000) [24353 gas]
    ├── ZrxAllowlist.isNonPayableAddr(_addr=Exchange) -> False [1155 gas]
    ├── ZrxAllowlist.isZrxAddr(_zrxAddr=Exchange) -> True [1177 gas]
    ├── Exchange.marketSellOrdersFillOrKill(
    │     orders=[
    │       [
    │         0x57845987C8C859D52931eE248D8d84aB10532407,
    │         DSProxy,
    │         0x1000000000000000000000000000000000000011,
    │         ZERO_ADDRESS,
    │         44587161153335369728,
    │         22021999999,
    │         0,
    │         0,
    │         1605676234,
    │         1605676134823,
    │         0xf4..6cc2,
    │         0xf4..1ec7,
    │         '',
    │         ''
    │       ],
    │       [
    │         0xC47b7094F378e54347e281AaB170E8ccA69d880A,
    │         ZERO_ADDRESS,
    │         ZERO_ADDRESS,
    │         ZERO_ADDRESS,
    │         44101517707448430621,
    │         22000000000,
    │         0,
    │         0,
    │         1605683335,
    │         45887941670002145135917800926357172768151492260295357762609187565998706361158,
    │         0xdc..6cc2,
    │         0xf4..1ec7,
    │         '',
    │         ''
    │       ]
    │     ],
    │     takerAssetFillAmount=21945000000,
    │     signatures=['0x1c..f103', "\'\\x04\'"]
    │   ) -> (
    │     makerAssetFilledAmount=44431261990481152968,
    │     takerAssetFilledAmount=21945000000,
    │     makerFeePaid=0,
    │     takerFeePaid=0,
    │     protocolFeePaid=6650000000000000
    │   ) [172105 gas] [0.02016 value]
    │   ├── (delegate) Exchange.fillOrder(
    │   │     order=[
    │   │       0x57845987C8C859D52931eE248D8d84aB10532407,
    │   │       DSProxy,
    │   │       0x1000000000000000000000000000000000000011,
    │   │       ZERO_ADDRESS,
    │   │       44587161153335369728,
    │   │       22021999999,
    │   │       0,
    │   │       0,
    │   │       1605676234,
    │   │       1605676134823,
    │   │       0xf4..6cc2,
    │   │       0xf4..1ec7,
    │   │       '',
    │   │       ''
    │   │     ],
    │   │     takerAssetFillAmount=21945000000,
    │   │     signature=0x1c..f103
    │   │   ) -> (
    │   │     makerAssetFilledAmount=44431261990481152968,
    │   │     takerAssetFilledAmount=21945000000,
    │   │     makerFeePaid=0,
    │   │     takerFeePaid=0,
    │   │     protocolFeePaid=6650000000000000
    │   │   ) [140727 gas] [0.02016 value]
    │   │   ├── CALL: ERC20Proxy.<0xa85e59e4>  [19278 gas]
    │   │   │   └── TetherToken.transferFrom(
    │   │   │         _from=DSProxy,
    │   │   │         _to=0x57845987C8C859D52931eE248D8d84aB10532407,
    │   │   │         _value=21945000000
    │   │   │       ) [17224 gas]
    │   │   ├── CALL: ERC20Proxy.<0xa85e59e4>  [33079 gas]
    │   │   │   └── WETH9.transferFrom(
    │   │   │         src=0x57845987C8C859D52931eE248D8d84aB10532407,
    │   │   │         dst=DSProxy,
    │   │   │         wad=44431261990481152968
    │   │   │       ) -> True [31025 gas]
    │   │   └── CALL: StakingProxy.<0xa3b4a327>  [20145 gas] [0.00665 value]
    │   │       └── (delegate) Staking.payProtocolFee(
    │   │             makerAddress=0x57845987C8C859D52931eE248D8d84aB10532407,
    │   │             payerAddress=DSProxy,
    │   │             protocolFee=6650000000000000
    │   │           ) [18173 gas] [0.00665 value]
    │   └── CALL: DSProxy  [40 gas] [0.01351 value]
    ├── TetherToken.balanceOf(who=DSProxy) -> 0 [2431 gas]
    ├── WETH9.balanceOf(DSProxy) -> 44431261990481152968 [1234 gas]
    ├── WETH9.withdraw(wad=44431261990481152968) [11880 gas]
    │   └── CALL: DSProxy  [40 gas] [44.43126199 value]
    ├── WETH9.balanceOf(DSProxy) -> 0 [1234 gas]
    ├── CEther.mint() [128739 gas] [44.42461199 value]
    │   ├── WhitePaperInterestRateModel.getBorrowRate(
    │   │     cash=1167291315524828085504226,
    │   │     borrows=51205735075389706087574,
    │   │     _reserves=98073114143716073182
    │   │   ) -> [0, 11511781014] [5403 gas]
    │   ├── CALL: Unitroller.<0x4ef4c3e1>  [48350 gas]
    │   │   └── (delegate) Comptroller.mintAllowed(
    │   │         cToken=CEther,
    │   │         minter=DSProxy,
    │   │         mintAmount=44424611990481152968
    │   │       ) -> 0 [46370 gas]
    │   │       ├── CEther.totalSupply() -> 6083183091150922 [1044 gas]
    │   │       ├── CEther.balanceOf(owner=DSProxy) -> 3588278641674 [1253 gas]
    │   │       ├── Comp.balanceOf(account=Unitroller) -> 37813854469600080464295 [1488 gas]
    │   │       └── Comp.transfer(dst=DSProxy, rawAmount=39357597512189848) -> True [10690 gas]
    │   └── CALL: Unitroller.<0x41c728b9>  [2316 gas]
    │       └── (delegate) Comptroller.mintVerify(
    │             cToken=CEther,
    │             minter=DSProxy,
    │             actualMintAmount=44424611990481152968,
    │             mintTokens=221801768562
    │           ) [403 gas]
    ├── CALL: 0x5668EAd1eDB8E2a4d724C8fb9cB5fFEabEB422dc  [0 gas] [0.02016 value]
    └── DefisaverLogger.Log(
          _contract=DSProxy,
          _caller=tx.origin,
          _logName="CompoundBoost",
          _data=0x00..1ec7
        ) [5060 gas]
"""
