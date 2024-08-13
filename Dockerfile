#---------------------------------------------------------------------------------------------
# See LICENSE in the project root for license information.
#---------------------------------------------------------------------------------------------

FROM ape:latest-slim

USER root

RUN pip install --upgrade pip
RUN pip install /wheels/*.whl

USER harambe

RUN ape --version
