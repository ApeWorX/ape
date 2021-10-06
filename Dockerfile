FROM ubuntu:20.04
RUN apt-get update && apt-get upgrade --yes && apt-get install python3-pip python3.8 --yes
COPY . /ape
RUN python3 /ape/setup.py
RUN ape plugins add ens --yes
RUN ape plugins add etherscan --yes
RUN ape plugins add infura --yes
RUN ape plugins add solidity --yes
RUN ape plugins add vyper --yes
ENTRYPOINT ["ape"]