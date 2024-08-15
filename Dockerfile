#---------------------------------------------------------------------------------------------
# See LICENSE in the project root for license information.
#---------------------------------------------------------------------------------------------

ARG PYTHON_VERSION="3.11"
FROM python:${PYTHON_VERSION} as builder

WORKDIR /wheels

RUN pip install --upgrade pip \
    && pip install wheel

COPY . .

RUN mkdir /wheels

COPY ./recommended-plugins.txt ./recommended-plugins.txt

RUN pip wheel .[recommended-plugins] --wheel-dir=/wheels

FROM ape:latest-slim

USER root

RUN pip install --upgrade pip
RUN pip install /wheels/*.whl

USER harambe

RUN ape --version
