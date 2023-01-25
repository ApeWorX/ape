#---------------------------------------------------------------------------------------------
# See LICENSE in the project root for license information.
#---------------------------------------------------------------------------------------------

ARG PYTHON_VERSION="3.9"
ARG PLUGINS_FILE="./recommended-plugins.txt"

FROM python:${PYTHON_VERSION}

RUN apt-get update && apt-get upgrade --yes && apt-get install git

# See http://label-schema.org for metadata schema
# TODO: Add `build-date` and `version`
LABEL maintainer="ApeWorX" \
      org.label-schema.schema-version="2.0" \
      org.label-schema.name="ape" \
      org.label-schema.description="Ape Ethereum Framework." \
      org.label-schema.url="https://docs.apeworx.io/ape/stable/" \
      org.label-schema.usage="https://docs.apeworx.io/ape/stable/userguides/quickstart.html#via-docker" \
      org.label-schema.vcs-url="https://github.com/ApeWorX/ape" \
      org.label-schema.docker.cmd="docker run --volume $HOME/.ape:/home/harambe/.ape --volume $HOME/.vvm:/home/harambe/.vvm --volume $HOME/.solcx:/home/harambe/.solcx --volume $PWD:/home/harambe/project --workdir /home/harambe/project apeworx/ape compile"

RUN useradd --create-home --shell /bin/bash harambe
WORKDIR /home/harambe
COPY . .

RUN pip install --upgrade pip \
    && pip install --no-cache-dir . \
    && pip install -r recommended-plugins.txt \
# Fix RLP installation issue
    && pip uninstall rlp --yes \
    && pip install rlp==3.0.0 \
# Validate installation
    && ape --version

USER harambe
ENTRYPOINT ["ape"]
