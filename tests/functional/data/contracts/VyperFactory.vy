# @version 0.4.0

event Deployment:
    target: address

@external
def create_contract(target: address) -> address:
    result: address = create_from_blueprint(target)
    log Deployment(result)
    return result
