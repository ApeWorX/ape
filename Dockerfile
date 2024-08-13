#---------------------------------------------------------------------------------------------
# See LICENSE in the project root for license information.
#---------------------------------------------------------------------------------------------

FROM ape:latest-slim

RUN pip install --upgrade pip
RUN pip install /wheels/*.whl

RUN ape --version
