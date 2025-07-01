import ape

local_variable = "test foo bar"
provider = ape.chain.provider
provider.set_timestamp(123123123123123123)
raise Exception("Expected exception")
