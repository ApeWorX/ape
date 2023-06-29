event Deployment:
    target: address


@external
def create_contract(target: address, _num: uint256) -> address:
    result: address = create_from_blueprint(target, _num, code_offset=3)
    log Deployment(result)
    return result
