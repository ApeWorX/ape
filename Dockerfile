FROM ubuntu:20.04
RUN apt-get update && apt-get upgrade --yes && apt-get install git python3.8 python3-pip --yes
COPY . .
RUN python3 ./setup.py install
RUN ape plugins add solidity --yes
RUN ape plugins add vyper --yes
RUN ape plugins add infura --yes
RUN ape plugins add etherscan --yes
RUN ape plugins add ens --yes
ENTRYPOINT ["ape"]
