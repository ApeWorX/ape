FROM ubuntu:22.04
RUN apt-get update && apt-get upgrade --yes && apt-get install git python3.9 python3-pip --yes
ADD . /code
WORKDIR /code

# need to use typing-extensions<4 to deal with issue 387 bug: Docker will not build
# TODO: Figure out a better solution or wait for it to resolve itself.
RUN pip install typing-extensions==3.10.0.2
RUN pip install .
RUN ape plugins install alchemy ens etherscan foundry hardhat infura ledger solidity template tokens trezor vyper
RUN pip install eth-rlp==0.3.0
ENTRYPOINT ["ape"]
