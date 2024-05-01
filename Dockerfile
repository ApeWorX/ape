#---------------------------------------------------------------------------------------------
# See LICENSE in the project root for license information.
#---------------------------------------------------------------------------------------------

ARG PYTHON_VERSION="3.11"
ARG PLUGINS_FILE="./recommended-plugins.txt"

FROM python:${PYTHON_VERSION} as builder

WORKDIR /wheels

COPY ./recommended-plugins.txt ./recommended-plugins.txt
COPY . .

RUN pip install --upgrade pip \
    && pip install wheel \
    && pip wheel .[recommended-plugins] --wheel-dir=/wheels

FROM python:${PYTHON_VERSION}-slim

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

COPY --from=builder /wheels /wheels
COPY ./recommended-plugins.txt ./recommended-plugins.txt

RUN pip install --upgrade pip \
    pip install --no-cache-dir --find-links=/wheels -r ./recommended-plugins.txt \
    && ape --version

WORKDIR /home/harambe/project
RUN chown --recursive harambe:harambe /home/harambe
USER harambe
ENTRYPOINT ["ape"]
