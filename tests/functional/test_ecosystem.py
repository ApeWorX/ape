from typing import Any, Dict

import pytest
from eth_typing import HexAddress, HexStr
from ethpm_types import HexBytes
from ethpm_types.abi import ABIType, MethodABI

from ape.api.networks import LOCAL_NETWORK_NAME
from ape.types import AddressType
from ape.utils import DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT
from ape_ethereum.ecosystem import Block
from ape_ethereum.transactions import TransactionType

LOG = {
    "removed": False,
    "logIndex": "0x0",
    "transactionIndex": "0x0",
    "transactionHash": "0x74dd040dfa06f0af9af8ca95d7aae409978400151c746f55ecce19e7356cfc5a",
    "blockHash": "0x2c99950b07accf3e442512a3352a11e6fed37b2331de5f71b7743b357d96e4e8",
    "blockNumber": "0xa946ac",
    "address": "0x274b028b03a250ca03644e6c578d81f019ee1323",
    "data": "0xabffd4675206dab5d04a6b0d62c975049665d1f512f29f303908abdd20bc08a100000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000060000000000000000000000000000000000000000000000000000000000000000744796e616d696300000000000000000000000000000000000000000000000000",  # noqa: E501
    "topics": [
        "0xa84473122c11e32cd505595f246a28418b8ecd6cf819f4e3915363fad1b8f968",
        "0x0000000000000000000000000000000000000000000000000000000000000006",
        "0x9f3d45ac20ccf04b45028b8080bb191eab93e29f7898ed43acf480dd80bba94d",
    ],
}


@pytest.fixture
def event_abi(vyper_contract_instance):
    return vyper_contract_instance.NumberChange.abi


@pytest.mark.parametrize(
    "address",
    (
        "0x63953eB1B3D8DB28334E7C1C69456C851F934199".lower(),
        0x63953EB1B3D8DB28334E7C1C69456C851F934199,
    ),
)
def test_decode_address(ethereum, address):
    expected = "0x63953eB1B3D8DB28334E7C1C69456C851F934199"
    actual = ethereum.decode_address(address)
    assert actual == expected


def test_encode_address(ethereum):
    raw_address = "0x63953eB1B3D8DB28334E7C1C69456C851F934199"
    address = AddressType(HexAddress(HexStr(raw_address)))
    actual = ethereum.encode_address(address)
    assert actual == raw_address


def test_encode_calldata(ethereum):
    abi = MethodABI(
        type="function",
        name="callMe",
        inputs=[
            ABIType(name="a", type="bytes4"),
            ABIType(name="b", type="address"),
            ABIType(name="c", type="uint256"),
            ABIType(name="d", type="bytes4[]"),
        ],
    )
    address = "0xd8da6bf26964af9d7eed9e03e53415d37aa96045"
    byte_array = ["0x456", "0x678"]
    values = ("0x123", address, HexBytes(55), byte_array)

    actual = ethereum.encode_calldata(abi, *values)
    expected = HexBytes(
        # 0x123
        "0123000000000000000000000000000000000000000000000000000000000000"
        # address
        "000000000000000000000000d8da6bf26964af9d7eed9e03e53415d37aa96045"
        # HexBytes(55)
        "0000000000000000000000000000000000000000000000000000000000000037"
        # byte_array
        "0000000000000000000000000000000000000000000000000000000000000080"
        "0000000000000000000000000000000000000000000000000000000000000002"
        "0456000000000000000000000000000000000000000000000000000000000000"
        "0678000000000000000000000000000000000000000000000000000000000000"
    )
    assert actual == expected


def test_block_handles_snake_case_parent_hash(eth_tester_provider, sender, receiver):
    # Transaction to change parent hash of next block
    sender.transfer(receiver, "1 gwei")

    # Replace 'parentHash' key with 'parent_hash'
    latest_block = eth_tester_provider.get_block("latest")
    latest_block_dict = eth_tester_provider.get_block("latest").dict()
    latest_block_dict["parent_hash"] = latest_block_dict.pop("parentHash")

    redefined_block = Block.parse_obj(latest_block_dict)
    assert redefined_block.parent_hash == latest_block.parent_hash


def test_transaction_acceptance_timeout(temp_config, config, networks):
    assert (
        networks.provider.network.transaction_acceptance_timeout
        == DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT
    )
    new_value = DEFAULT_LOCAL_TRANSACTION_ACCEPTANCE_TIMEOUT + 1
    timeout_config = {"ethereum": {"local": {"transaction_acceptance_timeout": new_value}}}
    with temp_config(timeout_config):
        assert networks.provider.network.transaction_acceptance_timeout == new_value


def test_decode_logs(ethereum, vyper_contract_instance):
    abi = vyper_contract_instance.NumberChange.abi
    result = [x for x in ethereum.decode_logs([LOG], abi)]
    assert len(result) == 1
    assert result[0] == {
        "event_name": "NumberChange",
        "contract_address": "0x274b028b03A250cA03644E6c578D81f019eE1323",
        "event_arguments": {
            "newNum": 6,
            "dynIndexed": HexBytes(
                "0x9f3d45ac20ccf04b45028b8080bb191eab93e29f7898ed43acf480dd80bba94d"
            ),
            "b": HexBytes("0xabffd4675206dab5d04a6b0d62c975049665d1f512f29f303908abdd20bc08a1"),
            "prevNum": 0,
            "dynData": "Dynamic",
        },
        "transaction_hash": "0x74dd040dfa06f0af9af8ca95d7aae409978400151c746f55ecce19e7356cfc5a",
        "block_number": 11093676,
        "block_hash": "0x2c99950b07accf3e442512a3352a11e6fed37b2331de5f71b7743b357d96e4e8",
        "log_index": 0,
        "transaction_index": 0,
    }


def test_decode_logs_empty_list(ethereum, event_abi):
    actual = [x for x in ethereum.decode_logs([], event_abi)]
    assert actual == []


def test_decode_block_when_hash_is_none(ethereum):
    # When using some providers, such as hardhat, the hash of the pending block is None
    block_data_with_none_hash: Dict[str, Any] = {
        "number": None,
        "hash": None,
        "parentHash": HexBytes(
            "0xcb94e150c06faee9ab2bf12a40b0937ac9eab1879c733ebe3249aafbba2f80b1"
        ),
        "nonce": None,
        "mixHash": None,
        "sha3Uncles": HexBytes(
            "0x1dcc4de8dec75d7aab85b567b6ccd41ad312451b948a7413f0a142fd40d49347"
        ),
        "logsBloom": None,
        "transactionsRoot": HexBytes(
            "0x56e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421"
        ),
        "stateRoot": HexBytes("0x8728474146565003152f9cee496de043fd68566dabdb06116a0d5bfc63e1a5a9"),
        "receiptsRoot": HexBytes(
            "0x56e81f171bcc55a6ff8345e692c0f86e5b48e01b996cadc001622fb5e363b421"
        ),
        "miner": "0xC014BA5EC014ba5ec014Ba5EC014ba5Ec014bA5E",
        "difficulty": 131072,
        "totalDifficulty": 131073,
        "extraData": HexBytes("0x"),
        "size": 513,
        "gasLimit": 30000000,
        "gasUsed": 0,
        "timestamp": 1660932629,
        "transactions": [],
        "uncles": [],
        "baseFeePerGas": 0,
    }
    actual = ethereum.decode_block(block_data_with_none_hash)
    assert actual.hash is None


def test_decode_receipt(eth_tester_provider, ethereum):
    receipt_data = {
        "provider": eth_tester_provider,
        "required_confirmations": 0,
        "blockHash": HexBytes("0x8988adc8a0b346526f1d769841b7464e38a282b25ed346f1f810be8cb7393bc2"),
        "blockNumber": 2,
        "from": "0x318b469BBa396AEc2C60342F9441be36A1945174",
        "gas": 1764431,
        "hash": HexBytes("0x58d086e6b7ecf55c92a5fe420d870ff2eebe99824a711a3cdbe29f497a0e534c"),
        "input": "0x3461169d573360005560016005556000600655600261040655600061040755600161040855600361080755600061080855600161080955600261080a55610c08546103ff811161169d5760018101610c0855610c038102610c09016005548082558060051b60018301600082601f0160051c610400811161169d57801561009657905b806006015481840155600101818118610082575b505050505061040654806104018301558060051b6001610401840101600082601f0160051c610400811161169d5780156100e157905b806104070154818401556001018181186100cc575b505050505061080754806108028301558060051b6001610802840101600082601f0160051c610400811161169d57801561012c57905b80610808015481840155600101818118610117575b5050505050505062301809546103ff811161169d57600181016230180955610c0381026230180a016005548082558060051b60018301600082601f0160051c610400811161169d57801561019057905b80600601548184015560010181811861017c575b505050505061040654806104018301558060051b6001610401840101600082601f0160051c610400811161169d5780156101db57905b806104070154818401556001018181186101c6575b505050505061080754806108028301558060051b6001610802840101600082601f0160051c610400811161169d57801561022657905b80610808015481840155600101818118610211575b5050505050505062301809546103ff811161169d57600181016230180955610c0381026230180a016005548082558060051b60018301600082601f0160051c610400811161169d57801561028a57905b806006015481840155600101818118610276575b505050505061040654806104018301558060051b6001610401840101600082601f0160051c610400811161169d5780156102d557905b806104070154818401556001018181186102c0575b505050505061080754806108028301558060051b6001610802840101600082601f0160051c610400811161169d57801561032057905b8061080801548184015560010181811861030b575b5050505050505061136361033961000039611363610000f36003361161000c5761134b565b60003560e01c3461135157632beb1711811861007c57600436186113515760007f1a7c56fae0af54ebae73bc4699b9de9835e7bb86b050dff7e80695b633f17abd60006040a260017fe5299d63f5ecdd1740024ea0902bd82cc8dc6b51d69078e007096f907615ced560006040a2005b633fb5c1cb81186101e95760243618611351576000543318156100f657600b6040527f21617574686f72697a656400000000000000000000000000000000000000000060605260405060405180606001601f826000031636823750506308c379a06000526020602052601f19601f6040510116604401601cfd5b6005600435146113515760015460025560043560015560076080527f44796e616d69630000000000000000000000000000000000000000000000000060a05260808051602082012090506004357fa84473122c11e32cd505595f246a28418b8ecd6cf819f4e3915363fad1b8f9686060600143034060c05260025460e052806101005260076040527f44796e616d69630000000000000000000000000000000000000000000000000060605260408160c00181518082526020830160208301815181525050508051806020830101601f82600003163682375050601f19601f82516020010116905090508101905060c0a3005b63e30081a081186102445760243618611351576004358060a01c611351576040526040516003556040517f7ff7bacc6cd661809ed1ddce28d4ad2c5b37779b61b9e3235f8262be529101a960006060a2607b60605260206060f35b63e30443bc811861028d5760443618611351576004358060a01c611351576040526004604051602052600052604060002080546024358082018281106113515790509050815550005b6309b1b3f281186102b257600436186113515733604052600143034060605260406040f35b6302f487d681186102dc576004361861135157336040526001430340606052600160805260606040f35b63a420b5a58118610306576004361861135157600260405233606052600143034060805260606040f35b63e9f7fd1481186103355760043618611351573360405260014303406060526001608052600160a05260806040f35b63a2fbee5381186103645760043618611351576002604052600260605233608052600143034060a05260806040f35b6342ce1ec6811861039f57600436186113515760016040523360605260014303406080523360a052600143034060c052600260e05260c06040f35b63052f3e76811861040257600436186113515760208060405280604001600060008252600060006000600181116113515780156103ef57905b60008160051b6020870101526001018181186103d8575b5050810160200190509050810190506040f35b63b345ad96811861047d576004361861135157602080604052806040016000600160a052600160c052600060a0518084528060051b6000826001811161135157801561046757905b8060051b60c001518160051b60208901015260010181811861044a575b5050820160200191505090509050810190506040f35b6335417bf48118610506576004361861135157602080604052806040016000600360e052600161010052600261012052600361014052600060e0518084528060051b600082600381116113515780156104f057905b8060051b61010001518160051b6020890101526001018181186104d2575b5050820160200191505090509050810190506040f35b63a5b0930d8118610585576004361861135157602080604052806040016000600260c0523360e0523361010052600060c0518084528060051b6000826002811161135157801561056f57905b8060051b60e001518160051b602089010152600101818118610552575b5050820160200191505090509050810190506040f35b639bfb2ad8811861063e576004361861135157602080604052806040016000600261014052336101605260014303406101805260016101a052336101c05260014303406101e052600261020052600061014051808452606081026000826002811161135157801561062857905b606081026020880101606082026101600180518252602081015160208301526040810151604083015250506001018181186105f2575b5050820160200191505090509050810190506040f35b633ce80e9481186106795760043618611351576001604052336060526001430340608052600260a0523360c052600143034060e05260c06040f35b6343790b64811861069a576004361861135157610280366040376102806040f35b63d4d64b3581186106bb576004361861135157610500366040376105006040f35b63650543a381186106df576004361861135157607b60405261014160605260406040f35b63243e096381186106fe57600436186113515760403660403760406040f35b638ba6052d81186107c657600436186113515761028036604037336040526040516102c0526060516102e0526080516103005260a0516103205260c0516103405260e051610360526101005161038052610120516103a052610140516103c052610160516103e05261018051610400526101a051610420526101c051610440526101e051610460526102005161048052610220516104a052610240516104c052610260516104e05261028051610500526102a0516105205261028036610540376105006102c0f35b63ccd62aa481186107fd576004361861135157600160405260026060526003608052600460a052600560c052600660e05260c06040f35b636126c87f81186108b2576004361861135157602080604052806040016000600362010080526001620100a0526002620100c0526003620100e052600462010100526005620101205260066201014052600062010080518084528060061b600082610400811161135157801561089c57905b8060061b60208801018160061b620100a0018051825260208101516020830152505060010181811861086f575b5050820160200191505090509050810190506040f35b6394a66fc981186109d557600436186113515760208060405280604001606080825280820160006005548083528060051b600082610400811161135157801561091157905b80600601548160051b6020880101526001018181186108f7575b505082016020019150509050810190508060208301528082016000610406548083528060051b600082610400811161135157801561096657905b8061040701548160051b60208801015260010181811861094b575b505082016020019150509050810190508060408301528082016000610807548083528060051b60008261040081116113515780156109bb57905b8061080801548160051b6020880101526001018181186109a0575b505082016020019150509050810190509050810190506040f35b63abeb202281186111335760043618611351576020806040528060400160a08082528082016000610c08548083528060051b6000826104008111611351578015610b5157905b828160051b602088010152610c038102610c09018360208801016060808252808201600084548083528060051b6000826104008111611351578015610a7857905b8060018a0101548160051b602088010152600101818118610a5c575b505082016020019150509050810190508060208301526104018301818301600082548083528060051b6000826104008111611351578015610ad157905b806001880101548160051b602088010152600101818118610ab5575b5050820160200191505090509050810190508060408301526108028301818301600082548083528060051b6000826104008111611351578015610b2c57905b806001880101548160051b602088010152600101818118610b10575b5050820160200191505090509050810190509050905083019250600101818118610a1b575b50508201602001915050905081019050806020830152808201600062301809548083528060051b6000826104008111611351578015610cc357905b828160051b602088010152610c0381026230180a018360208801016060808252808201600084548083528060051b6000826104008111611351578015610bea57905b8060018a0101548160051b602088010152600101818118610bce575b505082016020019150509050810190508060208301526104018301818301600082548083528060051b6000826104008111611351578015610c4357905b806001880101548160051b602088010152600101818118610c27575b5050820160200191505090509050810190508060408301526108028301818301600082548083528060051b6000826104008111611351578015610c9e57905b806001880101548160051b602088010152600101818118610c82575b5050820160200191505090509050810190509050905083019250600101818118610b8c575b5050820160200191505090508101905080604083015280820160006260240a548083528060051b6000826104008111611351578015610e3557905b828160051b602088010152610c0381026260240b018360208801016060808252808201600084548083528060051b6000826104008111611351578015610d5c57905b8060018a0101548160051b602088010152600101818118610d40575b505082016020019150509050810190508060208301526104018301818301600082548083528060051b6000826104008111611351578015610db557905b806001880101548160051b602088010152600101818118610d99575b5050820160200191505090509050810190508060408301526108028301818301600082548083528060051b6000826104008111611351578015610e1057905b806001880101548160051b602088010152600101818118610df4575b5050820160200191505090509050810190509050905083019250600101818118610cfe575b5050820160200191505090508101905080606083015280820160006290300b548083528060051b6000826104008111611351578015610fa757905b828160051b602088010152610c0381026290300c018360208801016060808252808201600084548083528060051b6000826104008111611351578015610ece57905b8060018a0101548160051b602088010152600101818118610eb2575b505082016020019150509050810190508060208301526104018301818301600082548083528060051b6000826104008111611351578015610f2757905b806001880101548160051b602088010152600101818118610f0b575b5050820160200191505090509050810190508060408301526108028301818301600082548083528060051b6000826104008111611351578015610f8257905b806001880101548160051b602088010152600101818118610f66575b5050820160200191505090509050810190509050905083019250600101818118610e70575b50508201602001915050905081019050806080830152808201600062c03c0c548083528060051b600082610400811161135157801561111957905b828160051b602088010152610c03810262c03c0d018360208801016060808252808201600084548083528060051b600082610400811161135157801561104057905b8060018a0101548160051b602088010152600101818118611024575b505082016020019150509050810190508060208301526104018301818301600082548083528060051b600082610400811161135157801561109957905b806001880101548160051b60208801015260010181811861107d575b5050820160200191505090509050810190508060408301526108028301818301600082548083528060051b60008261040081116113515780156110f457905b806001880101548160051b6020880101526001018181186110d8575b5050820160200191505090509050810190509050905083019250600101818118610fe2575b505082016020019150509050810190509050810190506040f35b6399e74a4c81186111e25760043618611351576020806040528060400160006002620180805233620180a05233620180c05233620180e0526060366201810037600062018080518084526060810260008261040081116113515780156111cc57905b60608102602088010160608202620180a0018051825260208101516020830152604081015160408301525050600101818118611195575b5050820160200191505090509050810190506040f35b638da5cb5b811861120157600436186113515760005460405260206040f35b6323fd0e40811861122057600436186113515760015460405260206040f35b634825cf6f811861123f57600436186113515760025460405260206040f35b636cbceeec811861125e57600436186113515760035460405260206040f35b6327e235e381186112995760243618611351576004358060a01c61135157604052600460405160205260005260406000205460605260206060f35b63d3aaff6d81186112db576044361861135157610401600435600281116113515702600501602435815481101561135157600182010190505460405260206040f35b63ae8ef2cb811861134957608436186113515762300c01600435600481116113515702610c0801610c03602435825481101561135157026001820101905061040160443560028111611351570281019050606435815481101561135157600182010190505460405260206040f35b505b60006000fd5b600080fda165767970657283000306000b005b600080fd",  # noqa: E501
        "nonce": 1,
        "to": None,
        "transactionIndex": 0,
        "value": 0,
        "v": 1,
        "r": HexBytes("0xfa532141efbfa5bbeaa542cf68bfe5df97dd18b696b8a183f74714758a646238"),
        "s": HexBytes("0x1b80edf76bb6f0295ff847c1b99eb2928ea3533fe41125cfe0fa17fdc634b938"),
        "type": 2,
        "accessList": [],
        "chainId": 31337,
        "gasPrice": 0,
        "maxFeePerGas": 0,
        "maxPriorityFeePerGas": 0,
        "transactionHash": HexBytes(
            "0x58d086e6b7ecf55c92a5fe420d870ff2eebe99824a711a3cdbe29f497a0e534c"
        ),
        "cumulativeGasUsed": 1764431,
        "gasUsed": 1764431,
        "contractAddress": "0xC072c85922b7233998B2Ab990fEFdE80218Ca63F",
        "logs": [],
        "logsBloom": HexBytes(
            "0x00000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000000"  # noqa: E501
        ),
        "status": 1,
        "effectiveGasPrice": 0,
    }
    receipt = ethereum.decode_receipt(receipt_data)

    # Tests against bug where input data would come back improperly
    assert receipt.data == HexBytes(
        "0x3461169d573360005560016005556000600655600261040655600061040755600161040855600361080755600061080855600161080955600261080a55610c08546103ff811161169d5760018101610c0855610c038102610c09016005548082558060051b60018301600082601f0160051c610400811161169d57801561009657905b806006015481840155600101818118610082575b505050505061040654806104018301558060051b6001610401840101600082601f0160051c610400811161169d5780156100e157905b806104070154818401556001018181186100cc575b505050505061080754806108028301558060051b6001610802840101600082601f0160051c610400811161169d57801561012c57905b80610808015481840155600101818118610117575b5050505050505062301809546103ff811161169d57600181016230180955610c0381026230180a016005548082558060051b60018301600082601f0160051c610400811161169d57801561019057905b80600601548184015560010181811861017c575b505050505061040654806104018301558060051b6001610401840101600082601f0160051c610400811161169d5780156101db57905b806104070154818401556001018181186101c6575b505050505061080754806108028301558060051b6001610802840101600082601f0160051c610400811161169d57801561022657905b80610808015481840155600101818118610211575b5050505050505062301809546103ff811161169d57600181016230180955610c0381026230180a016005548082558060051b60018301600082601f0160051c610400811161169d57801561028a57905b806006015481840155600101818118610276575b505050505061040654806104018301558060051b6001610401840101600082601f0160051c610400811161169d5780156102d557905b806104070154818401556001018181186102c0575b505050505061080754806108028301558060051b6001610802840101600082601f0160051c610400811161169d57801561032057905b8061080801548184015560010181811861030b575b5050505050505061136361033961000039611363610000f36003361161000c5761134b565b60003560e01c3461135157632beb1711811861007c57600436186113515760007f1a7c56fae0af54ebae73bc4699b9de9835e7bb86b050dff7e80695b633f17abd60006040a260017fe5299d63f5ecdd1740024ea0902bd82cc8dc6b51d69078e007096f907615ced560006040a2005b633fb5c1cb81186101e95760243618611351576000543318156100f657600b6040527f21617574686f72697a656400000000000000000000000000000000000000000060605260405060405180606001601f826000031636823750506308c379a06000526020602052601f19601f6040510116604401601cfd5b6005600435146113515760015460025560043560015560076080527f44796e616d69630000000000000000000000000000000000000000000000000060a05260808051602082012090506004357fa84473122c11e32cd505595f246a28418b8ecd6cf819f4e3915363fad1b8f9686060600143034060c05260025460e052806101005260076040527f44796e616d69630000000000000000000000000000000000000000000000000060605260408160c00181518082526020830160208301815181525050508051806020830101601f82600003163682375050601f19601f82516020010116905090508101905060c0a3005b63e30081a081186102445760243618611351576004358060a01c611351576040526040516003556040517f7ff7bacc6cd661809ed1ddce28d4ad2c5b37779b61b9e3235f8262be529101a960006060a2607b60605260206060f35b63e30443bc811861028d5760443618611351576004358060a01c611351576040526004604051602052600052604060002080546024358082018281106113515790509050815550005b6309b1b3f281186102b257600436186113515733604052600143034060605260406040f35b6302f487d681186102dc576004361861135157336040526001430340606052600160805260606040f35b63a420b5a58118610306576004361861135157600260405233606052600143034060805260606040f35b63e9f7fd1481186103355760043618611351573360405260014303406060526001608052600160a05260806040f35b63a2fbee5381186103645760043618611351576002604052600260605233608052600143034060a05260806040f35b6342ce1ec6811861039f57600436186113515760016040523360605260014303406080523360a052600143034060c052600260e05260c06040f35b63052f3e76811861040257600436186113515760208060405280604001600060008252600060006000600181116113515780156103ef57905b60008160051b6020870101526001018181186103d8575b5050810160200190509050810190506040f35b63b345ad96811861047d576004361861135157602080604052806040016000600160a052600160c052600060a0518084528060051b6000826001811161135157801561046757905b8060051b60c001518160051b60208901015260010181811861044a575b5050820160200191505090509050810190506040f35b6335417bf48118610506576004361861135157602080604052806040016000600360e052600161010052600261012052600361014052600060e0518084528060051b600082600381116113515780156104f057905b8060051b61010001518160051b6020890101526001018181186104d2575b5050820160200191505090509050810190506040f35b63a5b0930d8118610585576004361861135157602080604052806040016000600260c0523360e0523361010052600060c0518084528060051b6000826002811161135157801561056f57905b8060051b60e001518160051b602089010152600101818118610552575b5050820160200191505090509050810190506040f35b639bfb2ad8811861063e576004361861135157602080604052806040016000600261014052336101605260014303406101805260016101a052336101c05260014303406101e052600261020052600061014051808452606081026000826002811161135157801561062857905b606081026020880101606082026101600180518252602081015160208301526040810151604083015250506001018181186105f2575b5050820160200191505090509050810190506040f35b633ce80e9481186106795760043618611351576001604052336060526001430340608052600260a0523360c052600143034060e05260c06040f35b6343790b64811861069a576004361861135157610280366040376102806040f35b63d4d64b3581186106bb576004361861135157610500366040376105006040f35b63650543a381186106df576004361861135157607b60405261014160605260406040f35b63243e096381186106fe57600436186113515760403660403760406040f35b638ba6052d81186107c657600436186113515761028036604037336040526040516102c0526060516102e0526080516103005260a0516103205260c0516103405260e051610360526101005161038052610120516103a052610140516103c052610160516103e05261018051610400526101a051610420526101c051610440526101e051610460526102005161048052610220516104a052610240516104c052610260516104e05261028051610500526102a0516105205261028036610540376105006102c0f35b63ccd62aa481186107fd576004361861135157600160405260026060526003608052600460a052600560c052600660e05260c06040f35b636126c87f81186108b2576004361861135157602080604052806040016000600362010080526001620100a0526002620100c0526003620100e052600462010100526005620101205260066201014052600062010080518084528060061b600082610400811161135157801561089c57905b8060061b60208801018160061b620100a0018051825260208101516020830152505060010181811861086f575b5050820160200191505090509050810190506040f35b6394a66fc981186109d557600436186113515760208060405280604001606080825280820160006005548083528060051b600082610400811161135157801561091157905b80600601548160051b6020880101526001018181186108f7575b505082016020019150509050810190508060208301528082016000610406548083528060051b600082610400811161135157801561096657905b8061040701548160051b60208801015260010181811861094b575b505082016020019150509050810190508060408301528082016000610807548083528060051b60008261040081116113515780156109bb57905b8061080801548160051b6020880101526001018181186109a0575b505082016020019150509050810190509050810190506040f35b63abeb202281186111335760043618611351576020806040528060400160a08082528082016000610c08548083528060051b6000826104008111611351578015610b5157905b828160051b602088010152610c038102610c09018360208801016060808252808201600084548083528060051b6000826104008111611351578015610a7857905b8060018a0101548160051b602088010152600101818118610a5c575b505082016020019150509050810190508060208301526104018301818301600082548083528060051b6000826104008111611351578015610ad157905b806001880101548160051b602088010152600101818118610ab5575b5050820160200191505090509050810190508060408301526108028301818301600082548083528060051b6000826104008111611351578015610b2c57905b806001880101548160051b602088010152600101818118610b10575b5050820160200191505090509050810190509050905083019250600101818118610a1b575b50508201602001915050905081019050806020830152808201600062301809548083528060051b6000826104008111611351578015610cc357905b828160051b602088010152610c0381026230180a018360208801016060808252808201600084548083528060051b6000826104008111611351578015610bea57905b8060018a0101548160051b602088010152600101818118610bce575b505082016020019150509050810190508060208301526104018301818301600082548083528060051b6000826104008111611351578015610c4357905b806001880101548160051b602088010152600101818118610c27575b5050820160200191505090509050810190508060408301526108028301818301600082548083528060051b6000826104008111611351578015610c9e57905b806001880101548160051b602088010152600101818118610c82575b5050820160200191505090509050810190509050905083019250600101818118610b8c575b5050820160200191505090508101905080604083015280820160006260240a548083528060051b6000826104008111611351578015610e3557905b828160051b602088010152610c0381026260240b018360208801016060808252808201600084548083528060051b6000826104008111611351578015610d5c57905b8060018a0101548160051b602088010152600101818118610d40575b505082016020019150509050810190508060208301526104018301818301600082548083528060051b6000826104008111611351578015610db557905b806001880101548160051b602088010152600101818118610d99575b5050820160200191505090509050810190508060408301526108028301818301600082548083528060051b6000826104008111611351578015610e1057905b806001880101548160051b602088010152600101818118610df4575b5050820160200191505090509050810190509050905083019250600101818118610cfe575b5050820160200191505090508101905080606083015280820160006290300b548083528060051b6000826104008111611351578015610fa757905b828160051b602088010152610c0381026290300c018360208801016060808252808201600084548083528060051b6000826104008111611351578015610ece57905b8060018a0101548160051b602088010152600101818118610eb2575b505082016020019150509050810190508060208301526104018301818301600082548083528060051b6000826104008111611351578015610f2757905b806001880101548160051b602088010152600101818118610f0b575b5050820160200191505090509050810190508060408301526108028301818301600082548083528060051b6000826104008111611351578015610f8257905b806001880101548160051b602088010152600101818118610f66575b5050820160200191505090509050810190509050905083019250600101818118610e70575b50508201602001915050905081019050806080830152808201600062c03c0c548083528060051b600082610400811161135157801561111957905b828160051b602088010152610c03810262c03c0d018360208801016060808252808201600084548083528060051b600082610400811161135157801561104057905b8060018a0101548160051b602088010152600101818118611024575b505082016020019150509050810190508060208301526104018301818301600082548083528060051b600082610400811161135157801561109957905b806001880101548160051b60208801015260010181811861107d575b5050820160200191505090509050810190508060408301526108028301818301600082548083528060051b60008261040081116113515780156110f457905b806001880101548160051b6020880101526001018181186110d8575b5050820160200191505090509050810190509050905083019250600101818118610fe2575b505082016020019150509050810190509050810190506040f35b6399e74a4c81186111e25760043618611351576020806040528060400160006002620180805233620180a05233620180c05233620180e0526060366201810037600062018080518084526060810260008261040081116113515780156111cc57905b60608102602088010160608202620180a0018051825260208101516020830152604081015160408301525050600101818118611195575b5050820160200191505090509050810190506040f35b638da5cb5b811861120157600436186113515760005460405260206040f35b6323fd0e40811861122057600436186113515760015460405260206040f35b634825cf6f811861123f57600436186113515760025460405260206040f35b636cbceeec811861125e57600436186113515760035460405260206040f35b6327e235e381186112995760243618611351576004358060a01c61135157604052600460405160205260005260406000205460605260206060f35b63d3aaff6d81186112db576044361861135157610401600435600281116113515702600501602435815481101561135157600182010190505460405260206040f35b63ae8ef2cb811861134957608436186113515762300c01600435600481116113515702610c0801610c03602435825481101561135157026001820101905061040160443560028111611351570281019050606435815481101561135157600182010190505460405260206040f35b505b60006000fd5b600080fda165767970657283000306000b005b600080fd"  # noqa: E501
    )


def test_configure_default_txn_type(temp_config, ethereum):
    config_dict = {"ethereum": {"mainnet_fork": {"default_transaction_type": 0}}}
    assert ethereum.default_transaction_type == TransactionType.DYNAMIC

    with temp_config(config_dict):
        ethereum._default_network = "mainnet-fork"
        assert ethereum.default_transaction_type == TransactionType.STATIC
        ethereum._default_network = LOCAL_NETWORK_NAME
