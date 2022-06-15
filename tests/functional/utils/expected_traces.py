LOCAL_TRACE = """
Call trace for '0xbf6c0da1aaf504d3d1a6dcfa37d30bae25a05931eef142994225c313fcc28cd8'
txn.origin=0xc89D42189f0450C2b2c3c61f58Ec5d628176A1E7
ContractA.goodbye() [31011 gas]
├── SYMBOL.methodB1(lolol="ice-cream", dynamo=36) [401697 gas]
│   ├── ContractC.getSomeList() -> [
│   │     3425311345134513461345134534531452345,
│   │     111344445534535353,
│   │     993453434534534534534977788884443333
│   │   ] [369738 gas]
│   └── ContractC.methodC1(windows95="simpler", jamaica=36, cardinal=ContractA) [363505 gas]
├── SYMBOL.callMe(blue=0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C) -> 0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C [233062 gas]
├── SYMBOL.methodB2(trombone=0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C) [231581 gas]
│   ├── ContractC.paperwork(ContractA) -> (os="simpler", country=36, wings=ContractA) [226996 gas]
│   ├── ContractC.methodC1(windows95="simpler", jamaica=0, cardinal=ContractC) [221899 gas]
│   ├── ContractC.methodC2() [146872 gas]
│   └── ContractC.methodC2() [121652 gas]
├── ContractC.addressToValue(0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C) -> 0 [99935 gas]
├── SYMBOL.bandPractice(0x1e59ce931B4CFea3fe4B875411e280e173cB7A9C) -> 0 [93900 gas]
├── SYMBOL.methodB1(lolol="lemondrop", dynamo=0) [91930 gas]
│   ├── ContractC.getSomeList() -> [
│   │     3425311345134513461345134534531452345,
│   │     111344445534535353,
│   │     993453434534534534534977788884443333
│   │   ] [86116 gas]
│   └── ContractC.methodC1(windows95="simpler", jamaica=0, cardinal=ContractA) [82344 gas]
└── SYMBOL.methodB1(lolol="snitches_get_stiches", dynamo=111) [54861 gas]
    ├── ContractC.getSomeList() -> [
    │     3425311345134513461345134534531452345,
    │     111344445534535353,
    │     993453434534534534534977788884443333
    │   ] [51694 gas]
    └── ContractC.methodC1(windows95="simpler", jamaica=111, cardinal=ContractA) [47921 gas]
"""
FAIL_TRACE = """
Call trace for '0x053cba5c12172654d894f66d5670bab6215517a94189a9ffc09bc40a589ec04d'
🚫 reverted with message: "UNIV3R: min return"
txn.origin=0xd2f91C13e2D7ABbA4408Cd3D86285b7835524ad7
AggregationRouterV4.uniswapV3Swap(
  amount=12851675475480000000000,
  minReturn=4205588148,
  pools=[
    682631518358379038160760928734868612545194078373,
    57896044618658097711785492505125519847138076855409017373413004167987775624768
  ]
) [208466 gas]
├── CALL: 0x77924185CF0cbB2Ae0b746A0086A065d6875b0a5.<0x128acb08>  [235702 gas]
│   ├── WETH.transfer(dst=AggregationRouterV4, wad=2098831888913057968) -> True [198998 gas]
│   ├── XDEFI.balanceOf(account=0x77924185CF0cbB2Ae0b746A0086A065d6875b0a5) -> 1300692354907962674610343 [166172 gas]
│   │   └── (delegate) FixedToken.balanceOf(account=0x77924185CF0cbB2Ae0b746A0086A065d6875b0a5) -> 1300692354907962674610343 [161021 gas]
│   ├── AggregationRouterV4.uniswapV3SwapCallback(
│   │     amount0Delta=12851675475480000000000,
│   │     amount1Delta=-2098831888913057968,
│   │     0x00..4ad7
│   │   ) [157874 gas]
│   │   ├── STATICCALL: 0x77924185CF0cbB2Ae0b746A0086A065d6875b0a5.<0x0dfe1681>  [154703 gas]
│   │   ├── STATICCALL: 0x77924185CF0cbB2Ae0b746A0086A065d6875b0a5.<0xd21220a7>  [154293 gas]
│   │   ├── STATICCALL: 0x77924185CF0cbB2Ae0b746A0086A065d6875b0a5.<0xddca3f43>  [153845 gas]
│   │   └── XDEFI.transferFrom(
│   │         sender=tx.origin,
│   │         recipient=0x77924185CF0cbB2Ae0b746A0086A065d6875b0a5,
│   │         amount=12851675475480000000000
│   │       ) -> True [152092 gas]
│   │       └── (delegate) FixedToken.transferFrom(
│   │             sender=tx.origin,
│   │             recipient=0x77924185CF0cbB2Ae0b746A0086A065d6875b0a5,
│   │             amount=12851675475480000000000
│   │           ) -> True [149572 gas]
│   └── XDEFI.balanceOf(account=0x77924185CF0cbB2Ae0b746A0086A065d6875b0a5) -> 1313544030383442674610343 [135118 gas]
│       └── (delegate) FixedToken.balanceOf(account=0x77924185CF0cbB2Ae0b746A0086A065d6875b0a5) -> 1313544030383442674610343 [132875 gas]
└── CALL: 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640.<0x128acb08>  [130650 gas]
    ├── CALL: FiatTokenProxy.<0xa9059cbb>  [102998 gas]
    │   └── (delegate) FiatTokenV2_1.transfer(to=tx.origin, value=4192051335) -> True [94297 gas]
    ├── WETH.balanceOf(0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640) -> 68357784800426962457000 [73171 gas]
    ├── AggregationRouterV4.uniswapV3SwapCallback(
    │     amount0Delta=-4192051335,
    │     amount1Delta=2098831888913057968,
    │     0x00..097d
    │   ) [69917 gas]
    │   ├── STATICCALL: 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640.<0x0dfe1681>  [68120 gas]
    │   ├── STATICCALL: 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640.<0xd21220a7>  [67710 gas]
    │   ├── STATICCALL: 0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640.<0xddca3f43>  [67262 gas]
    │   └── WETH.transfer(
    │         dst=0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640,
    │         wad=2098831888913057968
    │       ) -> True [65595 gas]
    └── WETH.balanceOf(0x88e6A0c2dDD26FEEb64F039a2c41296FcB3f5640) -> 68359883632315875514968 [59578 gas]
"""
INTERNAL_TRANSFERS_TXN_0_TRACE = """
Call trace for '0xb7d7f1d5ce7743e821d3026647df486f517946ef1342a1ae93c96e4a8016eab7'
tx.origin=0x5668EAd1eDB8E2a4d724C8fb9cB5fFEabEB422dc
DSProxy.execute(_target=LoanShifterTaker, _data=0x35..0000) -> '' [1275643 gas]
└── LoanShifterTaker.moveLoan(
      _exchangeData=[
        0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE,
        0x0000000000000000000000000000000000000000,
        0,
        0,
        0,
        0x0000000000000000000000000000000000000000,
        0x0000000000000000000000000000000000000000,
        '',
        0
      ],
      _loanShift=[
        0,
        1,
        0,
        True,
        322647834938052117610,
        48354766774065079392000,
        Dai,
        CErc20Delegator,
        GemJoin,
        CEther,
        11598,
        0
      ]
    ) [1579778 gas]
    ├── GasToken2.balanceOf(owner=DSProxy) -> 0 [1550845 gas]
    ├── ShifterRegistry.getAddr(_contractName="MCD_SHIFTER") -> McdShifter [1547186 gas]
    ├── McdShifter.getLoanAmount(_cdpId=11598, _joinAddr=Dai) -> 48354786024690521017562 [1543624 gas]
    │   ├── DssCdpManager.ilks(11598) -> 'ETH-A' [1517521 gas]
    │   ├── Vat.ilks('ETH-A') -> (
    │   │     Art=333364930546330776399823641,
    │   │     rate=1021289223898672834155324367,
    │   │     spot=247460000000000000000000000000,
    │   │     line=540000000000000000000000000000000000000000000000000000,
    │   │     dust=100000000000000000000000000000000000000000000000
    │   │   ) [1514626 gas]
    │   ├── DssCdpManager.urns(11598) -> UrnHandler [1508213 gas]
    │   ├── Vat.urns('ETH-A', UrnHandler) -> (ink=322647834938052117611, art=47346809202686778770770) [1505140 gas]
    │   ├── DssCdpManager.urns(11598) -> UrnHandler [1501218 gas]
    │   └── Vat.dai(UrnHandler) -> 802993823174527025406118085 [1498156 gas]
    ├── ShifterRegistry.getAddr(_contractName="LOAN_SHIFTER_RECEIVER") -> LoanShifterReceiver [1513897 gas]
    ├── CALL: LoanShifterReceiver [3000 gas]
    ├── DSProxy.authority() -> DSGuard [1509589 gas]
    ├── DSGuard.permit(src=LoanShifterReceiver, dst=DSProxy, sig=0x1c..0000) [1506402 gas]
    ├── CALL: InitializableAdminUpgradeabilityProxy.<0x5cffe9de> [1478494 gas]
    │   └── LendingPool.flashLoan(
    │         _receiver=LoanShifterReceiver,
    │         _reserve=Dai,
    │         _amount=48354786024690521017562,
    │         _params=0x00..0000
    │       ) [1452618 gas]
    │       ├── STATICCALL: InitializableAdminUpgradeabilityProxy.<0x05075d6e> [1421040 gas]
    │       │   └── LendingPoolCore.getReserveIsActive(_reserve=Dai) -> True [1396219 gas]
    │       ├── Dai.balanceOf(InitializableAdminUpgradeabilityProxy) -> 10684533234693042314924969 [1414582 gas]
    │       ├── STATICCALL: InitializableAdminUpgradeabilityProxy.<0x586feb40> [1410882 gas]
    │       │   └── LendingPoolParametersProvider.getFlashLoanFeesInBips() -> [9, 3000] [1386223 gas]
    │       ├── CALL: InitializableAdminUpgradeabilityProxy.<0xfa93b2a5> [1404860 gas]
    │       │   └── LendingPoolCore.transferToUser(
    │       │         _reserve=Dai,
    │       │         _user=LoanShifterReceiver,
    │       │         _amount=48354786024690521017562
    │       │       ) [1380252 gas]
    │       │       └── Dai.transfer(dst=LoanShifterReceiver, wad=48354786024690521017562) -> True [1355286 gas]
    │       ├── LoanShifterReceiver.executeOperation(
    │       │     _reserve=Dai,
    │       │     _amount=48354786024690521017562,
    │       │     _fee=43519307422221468915,
    │       │     _params=0x00..0000
    │       │   ) [1365176 gas]
    │       │   ├── ShifterRegistry.getAddr(_contractName="MCD_SHIFTER") -> McdShifter [1334090 gas]
    │       │   ├── ShifterRegistry.getAddr(_contractName="COMP_SHIFTER") -> CompShifter [1330143 gas]
    │       │   ├── Dai.transfer(dst=DSProxy, wad=48354786024690521017562) -> True [1325760 gas]
    │       │   ├── CALL: DSProxy [3000 gas]
    │       │   ├── DSProxy.execute(_target=McdShifter, _data=0x8d..046a) -> '' [1296546 gas]
    │       │   │   ├── DSGuard.canCall(src_=LoanShifterReceiver, dst_=DSProxy, sig=0x1cff79cd) -> True [1271307 gas]
    │       │   │   └── McdShifter.close(
    │       │   │         _cdpId=11598,
    │       │   │         _joinAddr=GemJoin,
    │       │   │         _loanAmount=48354786024690521017562,
    │       │   │         _collateral=322647834938052117610
    │       │   │       ) [1263595 gas]
    │       │   │       ├── DssCdpManager.owns(11598) -> DSProxy [1241823 gas]
    │       │   │       ├── DSProxy.owner() -> tx.origin [1238873 gas]
    │       │   │       ├── DssCdpManager.ilks(11598) -> 'ETH-A' [1235815 gas]
    │       │   │       ├── DssCdpManager.vat() -> Vat [1232928 gas]
    │       │   │       ├── DssCdpManager.urns(11598) -> UrnHandler [1230064 gas]
    │       │   │       ├── Vat.urns('ETH-A', UrnHandler) -> (ink=322647834938052117611, art=47346809202686778770770) [1226950 gas]
    │       │   │       ├── Vat.ilks('ETH-A') -> (
    │       │   │       │     Art=333364930546330776399823641,
    │       │   │       │     rate=1021289223898672834155324367,
    │       │   │       │     spot=247460000000000000000000000000,
    │       │   │       │     line=540000000000000000000000000000000000000000000000000000,
    │       │   │       │     dust=100000000000000000000000000000000000000000000000
    │       │   │       │   ) [1223091 gas]
    │       │   │       ├── DssCdpManager.urns(11598) -> UrnHandler [1216363 gas]
    │       │   │       ├── Vat.ilks('ETH-A') -> (
    │       │   │       │     Art=333364930546330776399823641,
    │       │   │       │     rate=1021289223898672834155324367,
    │       │   │       │     spot=247460000000000000000000000000,
    │       │   │       │     line=540000000000000000000000000000000000000000000000000000,
    │       │   │       │     dust=100000000000000000000000000000000000000000000000
    │       │   │       │   ) [1213226 gas]
    │       │   │       ├── Vat.urns('ETH-A', UrnHandler) -> (ink=322647834938052117611, art=47346809202686778770770) [1206844 gas]
    │       │   │       ├── Vat.dai(UrnHandler) -> 802993823174527025406118085 [1202964 gas]
    │       │   │       ├── Dai.allowance(DSProxy, DaiJoin) -> 0 [1199562 gas]
    │       │   │       ├── Dai.approve(
    │       │   │       │     usr=DaiJoin,
    │       │   │       │     wad=115792089237316195423570985008687907853269984665640564039457584007913129639935
    │       │   │       │   ) -> True [1196465 gas]
    │       │   │       ├── DaiJoin.join(usr=UrnHandler, wad=48354786024690521017562) [1172639 gas]
    │       │   │       │   ├── Vat.move(
    │       │   │       │   │     src=DaiJoin,
    │       │   │       │   │     dst=UrnHandler,
    │       │   │       │   │     rad=48354786024690521017562000000000000000000000000000
    │       │   │       │   │   ) [1151523 gas]
    │       │   │       │   └── Dai.burn(usr=DSProxy, wad=48354786024690521017562) [1131471 gas]
    │       │   │       ├── Vat.dai(UrnHandler) -> 48354786024690521017562802993823174527025406118085 [1132005 gas]
    │       │   │       ├── Vat.ilks('ETH-A') -> (
    │       │   │       │     Art=333364930546330776399823641,
    │       │   │       │     rate=1021289223898672834155324367,
    │       │   │       │     spot=247460000000000000000000000000,
    │       │   │       │     line=540000000000000000000000000000000000000000000000000000,
    │       │   │       │     dust=100000000000000000000000000000000000000000000000
    │       │   │       │   ) [1129085 gas]
    │       │   │       ├── Vat.urns('ETH-A', UrnHandler) -> (ink=322647834938052117611, art=47346809202686778770770) [1122703 gas]
    │       │   │       ├── DssCdpManager.frob(cdp=11598, dink=0, dart=-47346809202686778770770) [1118678 gas]
    │       │   │       │   └── Vat.frob(
    │       │   │       │         i='ETH-A',
    │       │   │       │         u=UrnHandler,
    │       │   │       │         v=UrnHandler,
    │       │   │       │         w=UrnHandler,
    │       │   │       │         dink=0,
    │       │   │       │         dart=-47346809202686778770770
    │       │   │       │       ) [1095663 gas]
    │       │   │       ├── DssCdpManager.frob(cdp=11598, dink=-322647834938052117610, dart=0) [1064536 gas]
    │       │   │       │   └── Vat.frob(
    │       │   │       │         i='ETH-A',
    │       │   │       │         u=UrnHandler,
    │       │   │       │         v=UrnHandler,
    │       │   │       │         w=UrnHandler,
    │       │   │       │         dink=-322647834938052117610,
    │       │   │       │         dart=0
    │       │   │       │       ) [1042367 gas]
    │       │   │       ├── DssCdpManager.flux(cdp=11598, dst=DSProxy, wad=322647834938052117610) [999964 gas]
    │       │   │       │   └── Vat.flux(
    │       │   │       │         ilk='ETH-A',
    │       │   │       │         src=UrnHandler,
    │       │   │       │         dst=DSProxy,
    │       │   │       │         wad=322647834938052117610
    │       │   │       │       ) [978844 gas]
    │       │   │       ├── GemJoin.dec() -> 18 [959971 gas]
    │       │   │       ├── GemJoin.exit(usr=DSProxy, wad=322647834938052117610) [957179 gas]
    │       │   │       │   ├── Vat.slip(ilk='ETH-A', usr=DSProxy, wad=-322647834938052117610) [938667 gas]
    │       │   │       │   └── WETH9.transfer(dst=DSProxy, wad=322647834938052117610) -> True [928712 gas]
    │       │   │       ├── GemJoin.gem() -> WETH9 [907991 gas]
    │       │   │       ├── GemJoin.gem() -> WETH9 [905041 gas]
    │       │   │       ├── WETH9.withdraw(wad=322647834938052117610) [902143 gas]
    │       │   │       │   └── CALL: DSProxy [9700 gas]
    │       │   │       ├── GemJoin.gem() -> WETH9 [888841 gas]
    │       │   │       └── CALL: LoanShifterReceiver [9700 gas]
    │       │   ├── CALL: DSProxy [9700 gas]
    │       │   ├── DSProxy.execute(_target=CompShifter, _data=0xf4..11cd) -> '' [909826 gas]
    │       │   │   ├── DSGuard.canCall(src_=LoanShifterReceiver, dst_=DSProxy, sig=0x1cff79cd) -> True [890636 gas]
    │       │   │   └── CompShifter.open(
    │       │   │         _cCollAddr=CEther,
    │       │   │         _cBorrowAddr=CErc20Delegator,
    │       │   │         _debtAmount=48398305332112742486477
    │       │   │       ) [883181 gas]
    │       │   │       ├── CErc20Delegator.underlying() -> Dai [867384 gas]
    │       │   │       ├── CALL: Unitroller.<0xc2998238> [864100 gas]
    │       │   │       │   └── Comptroller.enterMarkets(cTokens=['CEther']) -> [0] [848828 gas]
    │       │   │       ├── CEther.mint() [792439 gas]
    │       │   │       │   ├── WhitePaperInterestRateModel.getBorrowRate(
    │       │   │       │   │     cash=877351454208435550173127,
    │       │   │       │   │     borrows=71532761571023032787465,
    │       │   │       │   │     _reserves=85036995401300782846
    │       │   │       │   │   ) -> [0, 13098657989] [762396 gas]
    │       │   │       │   ├── CALL: Unitroller.<0x4ef4c3e1> [723939 gas]
    │       │   │       │   │   └── Comptroller.mintAllowed(
    │       │   │       │   │         cToken=CEther,
    │       │   │       │   │         minter=DSProxy,
    │       │   │       │   │         mintAmount=322647834938052117610
    │       │   │       │   │       ) -> 0 [710857 gas]
    │       │   │       │   │       ├── CEther.totalSupply() -> 4737635605632584 [694083 gas]
    │       │   │       │   │       └── CEther.balanceOf(owner=DSProxy) -> 0 [660582 gas]
    │       │   │       │   └── CALL: Unitroller.<0x41c728b9> [635900 gas]
    │       │   │       │       └── Comptroller.mintVerify(
    │       │   │       │             cToken=CEther,
    │       │   │       │             minter=DSProxy,
    │       │   │       │             actualMintAmount=322647834938052117610,
    │       │   │       │             mintTokens=1611076291918
    │       │   │       │           ) [624188 gas]
    │       │   │       ├── CALL: Unitroller.<0xc2998238> [642849 gas]
    │       │   │       │   └── Comptroller.enterMarkets(cTokens=['CErc20Delegator']) -> [0] [631034 gas]
    │       │   │       ├── CErc20Delegator.borrow(borrowAmount=48398305332112742486477) -> 0 [589960 gas]
    │       │   │       │   └── CDaiDelegate.borrow(borrowAmount=48398305332112742486477) -> 0 [578445 gas]
    │       │   │       │       ├── Pot.drip() -> 1018008449363110619399951035 [560289 gas]
    │       │   │       │       │   └── Vat.suck(u=Vow, v=Pot, rad=0) [535897 gas]
    │       │   │       │       ├── Pot.pie(CErc20Delegator) -> 284260123136722085910285951 [524992 gas]
    │       │   │       │       ├── Pot.chi() -> 1018008449363110619399951035 [522194 gas]
    │       │   │       │       ├── DAIInterestRateModelV3.getBorrowRate(
    │       │   │       │       │     cash=289379207170181335004456462,
    │       │   │       │       │     borrows=941810534050634017587632492,
    │       │   │       │       │     reserves=740992012814482879709740
    │       │   │       │       │   ) -> 18203490479 [516927 gas]
    │       │   │       │       ├── CALL: Unitroller.<0xda3d454c> [479751 gas]
    │       │   │       │       │   └── Comptroller.borrowAllowed(
    │       │   │       │       │         cToken=CErc20Delegator,
    │       │   │       │       │         borrower=DSProxy,
    │       │   │       │       │         borrowAmount=48398305332112742486477
    │       │   │       │       │       ) -> 0 [470485 gas]
    │       │   │       │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1008191000000000000 [457718 gas]
    │       │   │       │       │       ├── CEther.getAccountSnapshot(account=DSProxy) -> [
    │       │   │       │       │       │     0,
    │       │   │       │       │       │     1611076291918,
    │       │   │       │       │       │     0,
    │       │   │       │       │       │     200268501595128483184821061
    │       │   │       │       │       │   ] [448905 gas]
    │       │   │       │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CEther) -> 372470000000000000000 [437795 gas]
    │       │   │       │       │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207212981963466297091815184] [429670 gas]
    │       │   │       │       │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..f710 [420666 gas]
    │       │   │       │       │       │       └── CDaiDelegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207212981963466297091815184] [411653 gas]
    │       │   │       │       │       │           ├── Pot.pie(CErc20Delegator) -> 284260123136722085910285951 [399791 gas]
    │       │   │       │       │       │           └── Pot.chi() -> 1018008449363110619399951035 [396992 gas]
    │       │   │       │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1008191000000000000 [406426 gas]
    │       │   │       │       │       ├── CErc20Delegator.borrowIndex() -> 1043822572059955633 [396422 gas]
    │       │   │       │       │       └── CErc20Delegator.totalBorrows() -> 941810568339112196812875778 [391711 gas]
    │       │   │       │       ├── Pot.pie(CErc20Delegator) -> 284260123136722085910285951 [370881 gas]
    │       │   │       │       ├── Pot.chi() -> 1018008449363110619399951035 [368082 gas]
    │       │   │       │       ├── Pot.chi() -> 1018008449363110619399951035 [361087 gas]
    │       │   │       │       ├── Pot.exit(wad=47542145020890376480893) [358200 gas]
    │       │   │       │       │   └── Vat.move(
    │       │   │       │       │         src=Pot,
    │       │   │       │       │         dst=CErc20Delegator,
    │       │   │       │       │         rad=48398305332112742486477763707302301597839813074255
    │       │   │       │       │       ) [337234 gas]
    │       │   │       │       ├── DaiJoin.exit(usr=DSProxy, wad=48398305332112742486477) [319250 gas]
    │       │   │       │       │   ├── Vat.move(
    │       │   │       │       │   │     src=CErc20Delegator,
    │       │   │       │       │   │     dst=DaiJoin,
    │       │   │       │       │   │     rad=48398305332112742486477000000000000000000000000000
    │       │   │       │       │   │   ) [310617 gas]
    │       │   │       │       │   └── Dai.mint(usr=DSProxy, wad=48398305332112742486477) [298832 gas]
    │       │   │       │       └── CALL: Unitroller.<0x5c778605> [228678 gas]
    │       │   │       │           └── Comptroller.borrowVerify(
    │       │   │       │                 cToken=CErc20Delegator,
    │       │   │       │                 borrower=DSProxy,
    │       │   │       │                 borrowAmount=48398305332112742486477
    │       │   │       │               ) [223335 gas]
    │       │   │       ├── Dai.balanceOf(DSProxy) -> 48398305332112742486477 [240919 gas]
    │       │   │       └── Dai.transfer(dst=LoanShifterReceiver, wad=48398305332112742486477) -> True [238005 gas]
    │       │   ├── LendingPoolAddressesProvider.getLendingPoolCore() -> InitializableAdminUpgradeabilityProxy [237443 gas]
    │       │   └── Dai.transfer(
    │       │         dst=InitializableAdminUpgradeabilityProxy,
    │       │         wad=48398305332112742486477
    │       │       ) -> True [233519 gas]
    │       ├── Dai.balanceOf(InitializableAdminUpgradeabilityProxy) -> 10684576754000464536393884 [244972 gas]
    │       └── CALL: InitializableAdminUpgradeabilityProxy.<0x09ac2953> [241025 gas]
    │           └── LendingPoolCore.updateStateOnFlashLoan(
    │                 _reserve=Dai,
    │                 _availableLiquidityBefore=10684533234693042314924969,
    │                 _income=30463515195555028241,
    │                 _protocolFee=13055792226666440674
    │               ) [234627 gas]
    │               ├── LendingPoolAddressesProvider.getTokenDistributor() -> InitializableAdminUpgradeabilityProxy [227466 gas]
    │               ├── Dai.transfer(
    │               │     dst=InitializableAdminUpgradeabilityProxy,
    │               │     wad=13055792226666440674
    │               │   ) -> True [224005 gas]
    │               ├── Dai.balanceOf(InitializableAdminUpgradeabilityProxy) -> 10684563698208237869953210 [181734 gas]
    │               └── OptimizedReserveInterestRateStrategy.calculateInterestRates(
    │                     _reserve=Dai,
    │                     _availableLiquidity=10684594161723433424981451,
    │                     _totalBorrowsStable=4087641944510702330917327,
    │                     _totalBorrowsVariable=11620401514013264063886023,
    │                     _averageStableBorrowRate=75619477990158369945895021
    │                   ) -> (
    │                     currentLiquidityRate=39043727754079106944517822,
    │                     currentStableBorrowRate=79637571899426327680798964,
    │                     currentVariableBorrowRate=62077167215997382294265458
    │                   ) [176223 gas]
    │                   ├── LendingPoolAddressesProvider.getLendingRateOracle() -> LendingRateOracle [170119 gas]
    │                   └── LendingRateOracle.getMarketBorrowRate(_asset=Dai) -> 35000000000000000000000000 [167314 gas]
    ├── DSProxy.authority() -> DSGuard [185527 gas]
    ├── DSGuard.forbid(src=LoanShifterReceiver, dst=DSProxy, sig=0x1c..0000) [182344 gas]
    └── DefisaverLogger.Log(
          _contract=DSProxy,
          _caller=tx.origin,
          _logName="LoanShifter",
          _data=0x00..0000
        ) [174327 gas]
"""
INTERNAL_TRANSFERS_TXN_1_TRACE = """
Call trace for '0x0537316f37627655b7fe5e50e23f71cd835b377d1cde4226443c94723d036e32'
tx.origin=0x5668EAd1eDB8E2a4d724C8fb9cB5fFEabEB422dc
DSProxy.execute(_target=CompoundFlashLoanTaker, _data=0xf7..0000) -> <?> [1045273 gas]
└── CompoundFlashLoanTaker.boostWithLoan(
      _exData=[
        TetherToken,
        0xEeeeeEeeeEeEeeEeEeEeeEEEeeeeEeeeeeeeEEeE,
        22000000000,
        0,
        2004750000000000000000000000,
        UniswapV2Wrapper,
        Exchange,
        0xa6..ac67,
        2025000000000000000000000000
      ],
      _cAddresses=['CEther', 'CErc20Delegator'],
      _gasCost=0
    ) [1312251 gas]
    ├── GasToken2.balanceOf(owner=DSProxy) -> 0 [1287520 gas]
    ├── STATICCALL: Unitroller.<0x5ec88c79> [1284452 gas]
    │   └── Comptroller.getAccountLiquidity(account=DSProxy) -> [0, 100216217422739835644076, 0] [1262621 gas]
    │       ├── CEther.getAccountSnapshot(account=DSProxy) -> [
    │       │     0,
    │       │     3588278641674,
    │       │     0,
    │       │     200289710046448107458251737
    │       │   ] [1235911 gas]
    │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CEther) -> 493495000000000000000 [1224801 gas]
    │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207745199249144216861107666] [1216674 gas]
    │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..65d2 [1195374 gas]
    │       │       └── CDaiDelegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207745199249144216861107666] [1174257 gas]
    │       │           ├── Pot.pie(CErc20Delegator) -> 348786572743118506284050656 [1150479 gas]
    │       │           └── Pot.chi() -> 1018008449363110619399951035 [1147680 gas]
    │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1006638000000000000 [1193432 gas]
    │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [
    │       │     0,
    │       │     1997736502878,
    │       │     0,
    │       │     201101221772832467767996110
    │       │   ] [1185219 gas]
    │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..2ece [1164410 gas]
    │       │       └── CCompLikeDelegate.getAccountSnapshot(account=DSProxy) -> [
    │       │             0,
    │       │             1997736502878,
    │       │             0,
    │       │             201101221772832467767996110
    │       │           ] [1143776 gas]
    │       │           └── Uni.balanceOf(account=CErc20Delegator) -> 13055727130865547340833198 [1120522 gas]
    │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 3722050000000000000 [1165353 gas]
    │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 166685375217, 203684337093459] [1156445 gas]
    │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..0b53 [1136543 gas]
    │       │       └── CErc20Delegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 166685375217, 203684337093459] [1116345 gas]
    │       │           └── TetherToken.balanceOf(who=CErc20Delegator) -> 9409870971804 [1090788 gas]
    │       └── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1000000000000000000000000000000 [1134231 gas]
    ├── STATICCALL: Unitroller.<0x7dc0d1d0> [1166013 gas]
    │   └── Comptroller.oracle() -> UniswapAnchoredView [1146041 gas]
    ├── CErc20Delegator.accrueInterest() -> 0 [1161257 gas]
    │   └── CErc20Delegate.accrueInterest() -> 0 [1141314 gas]
    │       ├── TetherToken.balanceOf(who=CErc20Delegator) -> 9409870971804 [1120059 gas]
    │       └── JumpRateModelV2.getBorrowRate(
    │             cash=9409870971804,
    │             borrows=31969908998585,
    │             reserves=116282802900
    │           ) -> 18425955753 [1112812 gas]
    ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1000000000000000000000000000000 [1117347 gas]
    ├── TetherToken.balanceOf(who=InitializableAdminUpgradeabilityProxy) -> 7334120405865 [1112844 gas]
    ├── CALL: Unitroller.<0xc2998238> [1108001 gas]
    │   └── Comptroller.enterMarkets(cTokens=['CEther', 'CErc20Delegator']) -> [0, 0] [1088912 gas]
    ├── DSProxy.owner() -> tx.origin [1098515 gas]
    ├── STATICCALL: Unitroller.<0x5ec88c79> [1095429 gas]
    │   └── Comptroller.getAccountLiquidity(account=DSProxy) -> [0, 100215845790739835644076, 0] [1076551 gas]
    │       ├── CEther.getAccountSnapshot(account=DSProxy) -> [
    │       │     0,
    │       │     3588278641674,
    │       │     0,
    │       │     200289710046448107458251737
    │       │   ] [1052748 gas]
    │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CEther) -> 493495000000000000000 [1041639 gas]
    │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207745199249144216861107666] [1033512 gas]
    │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..65d2 [1015074 gas]
    │       │       └── CDaiDelegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207745199249144216861107666] [996774 gas]
    │       │           ├── Pot.pie(CErc20Delegator) -> 348786572743118506284050656 [975769 gas]
    │       │           └── Pot.chi() -> 1018008449363110619399951035 [972971 gas]
    │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1006638000000000000 [1010270 gas]
    │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [
    │       │     0,
    │       │     1997736502878,
    │       │     0,
    │       │     201101221772832467767996110
    │       │   ] [1002056 gas]
    │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..2ece [984109 gas]
    │       │       └── CCompLikeDelegate.getAccountSnapshot(account=DSProxy) -> [
    │       │             0,
    │       │             1997736502878,
    │       │             0,
    │       │             201101221772832467767996110
    │       │           ] [966293 gas]
    │       │           └── Uni.balanceOf(account=CErc20Delegator) -> 13055727130865547340833198 [945812 gas]
    │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 3722050000000000000 [982190 gas]
    │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 166685746849, 203684618567521] [973283 gas]
    │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..ff61 [956243 gas]
    │       │       └── CErc20Delegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 166685746849, 203684618567521] [938862 gas]
    │       │           └── TetherToken.balanceOf(who=CErc20Delegator) -> 9409870971804 [916078 gas]
    │       └── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1000000000000000000000000000000 [951068 gas]
    ├── STATICCALL: Unitroller.<0x7dc0d1d0> [976990 gas]
    │   └── Comptroller.oracle() -> UniswapAnchoredView [959972 gas]
    ├── CErc20Delegator.accrueInterest() -> 0 [972234 gas]
    │   └── CErc20Delegate.accrueInterest() -> 0 [955244 gas]
    ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1000000000000000000000000000000 [967355 gas]
    ├── CErc20Delegator.borrow(borrowAmount=22000000000) -> 0 [962907 gas]
    │   └── CErc20Delegate.borrow(borrowAmount=22000000000) -> 0 [945972 gas]
    │       ├── CALL: Unitroller.<0xda3d454c> [921048 gas]
    │       │   └── Comptroller.borrowAllowed(
    │       │         cToken=CErc20Delegator,
    │       │         borrower=DSProxy,
    │       │         borrowAmount=22000000000
    │       │       ) -> 0 [904886 gas]
    │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1000000000000000000000000000000 [885332 gas]
    │       │       ├── CEther.getAccountSnapshot(account=DSProxy) -> [
    │       │       │     0,
    │       │       │     3588278641674,
    │       │       │     0,
    │       │       │     200289710046448107458251737
    │       │       │   ] [875420 gas]
    │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CEther) -> 493495000000000000000 [864310 gas]
    │       │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207745199249144216861107666] [856183 gas]
    │       │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..65d2 [840516 gas]
    │       │       │       └── CDaiDelegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 0, 207745199249144216861107666] [824943 gas]
    │       │       │           ├── Pot.pie(CErc20Delegator) -> 348786572743118506284050656 [806623 gas]
    │       │       │           └── Pot.chi() -> 1018008449363110619399951035 [803824 gas]
    │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1006638000000000000 [832941 gas]
    │       │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [
    │       │       │     0,
    │       │       │     1997736502878,
    │       │       │     0,
    │       │       │     201101221772832467767996110
    │       │       │   ] [824728 gas]
    │       │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..2ece [809552 gas]
    │       │       │       └── CCompLikeDelegate.getAccountSnapshot(account=DSProxy) -> [
    │       │       │             0,
    │       │       │             1997736502878,
    │       │       │             0,
    │       │       │             201101221772832467767996110
    │       │       │           ] [794463 gas]
    │       │       │           └── Uni.balanceOf(account=CErc20Delegator) -> 13055727130865547340833198 [776667 gas]
    │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 3722050000000000000 [804862 gas]
    │       │       ├── CErc20Delegator.getAccountSnapshot(account=DSProxy) -> [0, 0, 166685746849, 203684618567521] [795955 gas]
    │       │       │   └── CErc20Delegator.delegateToImplementation(data=0xc3..52dd) -> 0x00..ff61 [781686 gas]
    │       │       │       └── CErc20Delegate.getAccountSnapshot(account=DSProxy) -> [0, 0, 166685746849, 203684618567521] [767032 gas]
    │       │       │           └── TetherToken.balanceOf(who=CErc20Delegator) -> 9409870971804 [746933 gas]
    │       │       ├── UniswapAnchoredView.getUnderlyingPrice(cToken=CErc20Delegator) -> 1000000000000000000000000000000 [773740 gas]
    │       │       ├── CErc20Delegator.borrowIndex() -> 1045063620842360840 [764592 gas]
    │       │       ├── CErc20Delegator.totalBorrows() -> 31969980276796 [759880 gas]
    │       │       ├── CErc20Delegator.borrowBalanceStored(account=DSProxy) -> 166685746849 [740564 gas]
    │       │       │   └── CErc20Delegator.delegateToImplementation(data=0x95..52dd) -> 0x00..a6a1 [727110 gas]
    │       │       │       └── CErc20Delegate.borrowBalanceStored(account=DSProxy) -> 166685746849 [713309 gas]
    │       │       ├── Comp.balanceOf(account=Unitroller) -> 37814309293046111340279 [727699 gas]
    │       │       └── Comp.transfer(dst=DSProxy, rawAmount=454823446030875984) -> True [724562 gas]
    │       ├── TetherToken.balanceOf(who=CErc20Delegator) -> 9409870971804 [727650 gas]
    │       ├── TetherToken.transfer(_to=DSProxy, _value=22000000000) [717512 gas]
    │       └── CALL: Unitroller.<0x5c778605> [667527 gas]
    │           └── Comptroller.borrowVerify(
    │                 cToken=CErc20Delegator,
    │                 borrower=DSProxy,
    │                 borrowAmount=22000000000
    │               ) [655327 gas]
    ├── CErc20Delegator.underlying() -> TetherToken [691250 gas]
    ├── BotRegistry.botList(tx.origin) -> False [688173 gas]
    ├── CErc20Delegator.underlying() -> TetherToken [685289 gas]
    ├── Discount.isCustomFeeSet(_user=tx.origin) -> False [682335 gas]
    ├── TetherToken.transfer(
    │     _to=0x322d58b9E75a6918f7e7849AEe0fF09369977e08,
    │     _value=55000000
    │   ) [678284 gas]
    ├── TetherToken.approve(_spender=ERC20Proxy, _value=0) [660219 gas]
    ├── TetherToken.approve(_spender=ERC20Proxy, _value=21945000000) [653617 gas]
    ├── ZrxAllowlist.isNonPayableAddr(_addr=Exchange) -> False [627556 gas]
    ├── ZrxAllowlist.isZrxAddr(_zrxAddr=Exchange) -> True [624511 gas]
    └── Exchange.marketSellOrdersFillOrKill(
          orders=[
            ['0x57845987C8C859D52931eE248D8d84aB10532407', 'DSProxy', '0x1000000000000000000000000000000000000011', '0x0000000000000000000000000000000000000000',
        44587161153335369728, 22021999999, 0, 0, 1605676234, 1605676134823, '0xf4..6cc2', '0xf4..1ec7', "''", "''"],
            ['DexForwarderBridge', '0x0000000000000000000000000000000000000000', '0x0000000000000000000000000000000000000000',
        '0x0000000000000000000000000000000000000000', 44101517707448430621, 22000000000, 0, 0, 1605683335,
        45887941670002145135917800926357172768151492260295357762609187565998706361158, '0xdc..6cc2', '0xf4..1ec7', "''", "''"]
          ],
          takerAssetFillAmount=21945000000,
          signatures=['0x1c..f103', "'\x04'"]
        ) -> <?> [617343 gas]
        ├── Exchange.fillOrder(
        │     order=[
        │       0x57845987C8C859D52931eE248D8d84aB10532407,
        │       DSProxy,
        │       0x1000000000000000000000000000000000000011,
        │       0x0000000000000000000000000000000000000000,
        │       44587161153335369728,
        │       22021999999,
        │       0,
        │       0,
        │       1605676234,
        │       1605676134823,
        │       0xf4..6cc2,
        │       0xf4..1ec7,
        │       '',
        │       ''
        │     ],
        │     takerAssetFillAmount=21945000000,
        │     signature=0x1c..f103
        │   ) -> (
        │     makerAssetFilledAmount=44431261990481152968,
        │     takerAssetFilledAmount=21945000000,
        │     makerFeePaid=0,
        │     takerFeePaid=0,
        │     protocolFeePaid=6650000000000000
        │   ) [581625 gas]
        │   ├── STATICCALL: 0x0000000000000000000000000000000000000001.<0xf535d8b5> [558935 gas]
        │   │   ├── CALL: ERC20Proxy.<0xa85e59e4> [521530 gas]
        │   │   │   └── TetherToken.transferFrom(
        │   │   │         _from=DSProxy,
        │   │   │         _to=0x57845987C8C859D52931eE248D8d84aB10532407,
        │   │   │         _value=21945000000
        │   │   │       ) [511431 gas]
        │   │   ├── CALL: ERC20Proxy.<0xa85e59e4> [499288 gas]
        │   │   │   └── WETH9.transferFrom(
        │   │   │         src=0x57845987C8C859D52931eE248D8d84aB10532407,
        │   │   │         dst=DSProxy,
        │   │   │         wad=44431261990481152968
        │   │   │       ) -> True [489536 gas]
        │   │   └── CALL: StakingProxy.<0xa3b4a327> [463535 gas]
        │   │       └── Staking.payProtocolFee(
        │   │             makerAddress=0x57845987C8C859D52931eE248D8d84aB10532407,
        │   │             payerAddress=DSProxy,
        │   │             protocolFee=6650000000000000
        │   │           ) [447862 gas]
        │   └── CALL: DSProxy [9700 gas]
        ├── TetherToken.balanceOf(who=DSProxy) -> 0 [439341 gas]
        ├── WETH9.balanceOf(DSProxy) -> 44431261990481152968 [435122 gas]
        ├── WETH9.withdraw(wad=44431261990481152968) [432235 gas]
        │   └── CALL: DSProxy [9700 gas]
        ├── WETH9.balanceOf(DSProxy) -> 0 [418116 gas]
        ├── CEther.mint() [415092 gas]
        │   ├── WhitePaperInterestRateModel.getBorrowRate(
        │   │     cash=1167291315524828085504226,
        │   │     borrows=51205735075389706087574,
        │   │     _reserves=98073114143716073182
        │   │   ) -> [0, 11511781014] [390945 gas]
        │   ├── CALL: Unitroller.<0x4ef4c3e1> [352488 gas]
        │   │   └── Comptroller.mintAllowed(
        │   │         cToken=CEther,
        │   │         minter=DSProxy,
        │   │         mintAmount=44424611990481152968
        │   │       ) -> 0 [345210 gas]
        │   │       ├── CEther.totalSupply() -> 6083183091150922 [334150 gas]
        │   │       ├── CEther.balanceOf(owner=DSProxy) -> 3588278641674 [315437 gas]
        │   │       ├── Comp.balanceOf(account=Unitroller) -> 37813854469600080464295 [311023 gas]
        │   │       └── Comp.transfer(dst=DSProxy, rawAmount=39357597512189848) -> True [307887 gas]
        │   └── CALL: Unitroller.<0x41c728b9> [278611 gas]
        │       └── Comptroller.mintVerify(
        │             cToken=CEther,
        │             minter=DSProxy,
        │             actualMintAmount=44424611990481152968,
        │             mintTokens=221801768562
        │           ) [272482 gas]
        └── CALL: 0x5668EAd1eDB8E2a4d724C8fb9cB5fFEabEB422dc [9700 gas]
            └── DefisaverLogger.Log(
                  _contract=DSProxy,
                  _caller=tx.origin,
                  _logName="CompoundBoost",
                  _data=0x00..1ec7
                ) [271885 gas]
"""
