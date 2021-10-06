FROM ubuntu:20.04
RUN apt-get update && apt-get upgrade --yes
RUN apt-get install python3-pip python3.8 --yes
RUN pip3 install --upgrade eth-ape
RUN ape plugins add ens --yes
RUN ape plugins add etherscan --yes
RUN ape plugins add infura --yes
RUN ape plugins add solidity --yes
RUN ape plugins add vyper --yes
ENTRYPOINT ["ape"]