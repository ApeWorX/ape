import ape


def main():
    local_variable = "test foo bar"  # noqa[F841]
    provider = ape.chain.provider
    provider.set_timestamp(123123123123123123)
    raise Exception("Expected exception")
