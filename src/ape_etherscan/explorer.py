from ape.api import ExplorerAPI

ETHERSCAN_URI = (
    lambda n: (f"https://{n}.etherscan.io/" if n != "mainnet" else "https://etherscan.io/")
    + "{0}/{1}/"
)


class Etherscan(ExplorerAPI):
    def get_address_url(self, address: str) -> str:
        return ETHERSCAN_URI(self.network.name).format("address", address)

    def get_transaction_url(self, transaction_hash: str) -> str:
        return ETHERSCAN_URI(self.network.name).format("tx", transaction_hash)
