FROM ubuntu:latest
RUN apt-get update && apt-get upgrade -y
RUN apt-get install python3-pip python3 python-is-python3 -y
RUN pip install --upgrade eth-ape
RUN ape plugins add ens -y
RUN ape plugins add etherscan -y
RUN ape plugins add infura -y
RUN ape plugins add solidity -y
RUN ape plugins add vyper -y
