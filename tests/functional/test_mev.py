from ape_ethereum.mev.calls import SimulationReport


def test_simulation_report():
    data = {
        "success": True,
        "stateBlock": "0xa",
        "mevGasPrice": "0x399339e8",
        "profit": "0x14537d8d4b310",
        "refundableValue": "0x14537d8d4b310",
        "gasUsed": "0x5a60a",
        "logs": [
            {
                "txLogs": [
                    {
                        "address": "0x5fbdb2315678afecb367f032d93f642f64180aa3",
                        "topics": [
                            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                            "0x0000000000000000000000009fe46736679d2d9a65f0992f2272de9f3c7fa6e0",
                            "0x0000000000000000000000003c44cdddb6a900fa2b585dd299e03d12fa4293bc",
                        ],
                        "data": "0x00000000000000000000000000000000000000000000000000000000000186a0",
                        "blockHash": None,
                        "blockNumber": None,
                        "transactionHash": "0x52a4d4f8e0411d06aa5b9bc6ab0a143716225ca8f16568739f80c22d31b8f450",
                        "transactionIndex": "0x0",
                        "logIndex": "0x0",
                        "removed": False,
                    }
                ]
            },
            {
                "txLogs": [
                    {
                        "address": "0xe7f1725e7734ce288f8367e1bb143e90bb3f0512",
                        "topics": [
                            "0xddf252ad1be2c89b69c2b068fc378daa952ba7f163c4a11628f55a4df523b3ef",
                            "0x0000000000000000000000003c44cdddb6a900fa2b585dd299e03d12fa4293bc",
                            "0x0000000000000000000000009fe46736679d2d9a65f0992f2272de9f3c7fa6e0",
                        ],
                        "data": "0x00000000000000000000000000000000000000000000000000000000000186a0",
                        "blockHash": None,
                        "blockNumber": None,
                        "transactionHash": "0xf678d62c462dc5a63504e1703822dc6740771a8cd4b57bf74f660e50792e3c40",
                        "transactionIndex": "0x1",
                        "logIndex": "0x1",
                        "removed": False,
                    }
                ]
            },
        ],
    }
    report = SimulationReport.model_validate(data)
    assert report.success
