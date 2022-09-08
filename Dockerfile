FROM ubuntu:22.04
RUN apt-get update && apt-get upgrade --yes && apt-get install git python3.9 python3-pip --yes
ADD . /code
WORKDIR /code

RUN pip install .
RUN ape plugins install alchemy ens etherscan foundry hardhat infura ledger solidity template tokens trezor vyper
RUN pip install eth-rlp==0.3.0
ENTRYPOINT ["ape"]
