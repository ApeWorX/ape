from eth_account import Account as EthAccount

try:
    # Web3 v7
    from web3.middleware import ExtraDataToPOAMiddleware  # type: ignore
except ImportError:
    from web3.middleware import geth_poa_middleware as ExtraDataToPOAMiddleware  # type: ignore

try:
    from web3.providers import WebsocketProviderV2 as WebsocketProvider  # type: ignore
except ImportError:
    from web3.providers import WebSocketProvider as WebsocketProvider  # type: ignore


def sign_hash(msghash, private_key):
    try:
        # Web3 v7
        return EthAccount.unsafe_sign_hash(msghash, private_key)  # type: ignore
    except AttributeError:
        # Web3 v6
        return EthAccount.signHash(msghash, private_key)  # type: ignore


__all__ = [
    "ExtraDataToPOAMiddleware",
    "sign_hash",
    "WebsocketProvider",
]
