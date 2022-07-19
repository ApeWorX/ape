# @version ^0.3.3

owner: public(address)
myNumber: public(uint256)
prevNumber: public(uint256)
theAddress: public(address)

event NumberChange:
    b: bytes32
    prevNum: uint256
    dynData: String[12]
    newNum: indexed(uint256)
    dynIndexed: indexed(String[12])

event AddressChange:
    newAddress: indexed(address)

event FooHappened:
    foo: indexed(uint256)

event BarHappened:
    bar: indexed(uint256)

struct MyStruct:
    a: address
    b: bytes32

struct NestedStruct1:
    t: MyStruct
    foo: uint256

struct NestedStruct2:
    foo: uint256
    t: MyStruct

struct WithArray:
    foo: uint256
    arr: MyStruct[2]
    bar: uint256

@external
def __init__():
    self.owner = msg.sender

@external
def fooAndBar():
    log FooHappened(0)
    log BarHappened(1)

@external
def setNumber(num: uint256):
    assert msg.sender == self.owner, "!authorized"
    assert num != 5
    self.prevNumber = self.myNumber
    self.myNumber = num
    log NumberChange(block.prevhash, self.prevNumber, "Dynamic", num, "Dynamic")

@external
def setAddress(_address: address):
    self.theAddress = _address
    log AddressChange(_address)

@view
@external
def getStruct() -> MyStruct:
    return MyStruct({a: msg.sender, b: block.prevhash})

@view
@external
def getNestedStruct1() -> NestedStruct1:
    return NestedStruct1({t: MyStruct({a: msg.sender, b: block.prevhash}), foo: 1})

@view
@external
def getNestedStruct2() -> NestedStruct2:
    return NestedStruct2({foo: 2, t: MyStruct({a: msg.sender, b: block.prevhash})})

@view
@external
def getNestedStructWithTuple1() -> (NestedStruct1, uint256):
    return (NestedStruct1({t: MyStruct({a: msg.sender, b: block.prevhash}), foo: 1}), 1)

@view
@external
def getNestedStructWithTuple2() -> (uint256, NestedStruct2):
    return (2, NestedStruct2({foo: 2, t: MyStruct({a: msg.sender, b: block.prevhash})}))

@view
@external
def getStructWithArray() -> WithArray:
    return WithArray(
        {
            foo: 1,
            arr: [
                MyStruct({a: msg.sender, b: block.prevhash}),
                MyStruct({a: msg.sender, b: block.prevhash})
            ],
            bar: 2
        }
    )

@pure
@external
def getEmptyList() -> DynArray[uint256, 1]:
    return []

@pure
@external
def getSingleItemList() -> DynArray[uint256, 1]:
    return [1]

@pure
@external
def getFilledList() -> DynArray[uint256, 3]:
    return [1, 2, 3]

@view
@external
def getAddressList() -> DynArray[address, 2]:
    return [msg.sender, msg.sender]


@view
@external
def getDynamicStructList() -> DynArray[NestedStruct1, 2]:
    return [
        NestedStruct1({t: MyStruct({a: msg.sender, b: block.prevhash}), foo: 1}),
        NestedStruct1({t: MyStruct({a: msg.sender, b: block.prevhash}), foo: 2})
    ]

@view
@external
def getStaticStructList() -> NestedStruct2[2]:
    return [
        NestedStruct2({foo: 1, t: MyStruct({a: msg.sender, b: block.prevhash})}),
        NestedStruct2({foo: 2, t: MyStruct({a: msg.sender, b: block.prevhash})})
    ]

@pure
@external
def getMultipleValues() -> (uint256, uint256):
    return (123, 321)
