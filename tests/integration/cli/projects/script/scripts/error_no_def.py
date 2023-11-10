import ape

local_variable = "test foo bar"  # noqa[F841]
acct = "0xd8dA6BF26964aF9D7eEd9e03E53415D37aA96045"
provider = ape.chain.provider
provider.set_balance(acct, 100000000)
raise Exception("Expected exception")
