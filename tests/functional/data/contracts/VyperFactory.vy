# @version 0.4.3

event Deployment:
    target: address

@external
def create_contract(target: address) -> address:
    result: address = create_from_blueprint(target)
    log Deployment(result)
    return result

@external
def create_proxy(_masterCopy: address) -> address:
    result: address = create_forwarder_to(_masterCopy)
    log Deployment(result)
    return result

