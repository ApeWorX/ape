event Log:
    addr: address

@external
def deploy(master_copy: address) -> address:
    addr: address = create_minimal_proxy_to(master_copy)
    log Log(addr)

    return addr
