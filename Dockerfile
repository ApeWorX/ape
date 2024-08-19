#---------------------------------------------------------------------------------------------
# See LICENSE in the project root for license information.
#---------------------------------------------------------------------------------------------

ARG SLIM_IMAGE
ARG PYTHON_VERSION="3.11"
FROM python:${PYTHON_VERSION} AS builder

WORKDIR /wheels

RUN pip install --upgrade pip \
    && pip install wheel

COPY . .

COPY ./recommended-plugins.txt ./recommended-plugins.txt

RUN pip wheel .[recommended-plugins] --wheel-dir=/wheels

FROM ${SLIM_IMAGE} AS ape_slim

USER root

COPY --from=builder /wheels/*.whl /wheels/

RUN pip install --upgrade pip
RUN pip install /wheels/*.whl

USER harambe

RUN ape --version
