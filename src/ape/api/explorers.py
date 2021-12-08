from . import networks
from .base import API, apimethod


class ExplorerAPI(API):
    """
    An Explorer must work with a particular Network in a particular Ecosystem
    """

    name: str  # Plugin name
    network: networks.NetworkAPI
    request_header: str

    @apimethod
    def get_address_url(self, address: str) -> str:
        ...

    @apimethod
    def get_transaction_url(self, transaction_hash: str) -> str:
        ...
