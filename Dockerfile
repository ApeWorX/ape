#---------------------------------------------------------------------------------------------
# See LICENSE in the project root for license information.
#---------------------------------------------------------------------------------------------
ARG SLIM_IMAGE
FROM ${SLIM_IMAGE} AS builder

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

WORKDIR /wheels

# Add the extras by installing them directly
# NOTE: Parse them from the already-installed Ape's "recommended-plugins" extra
RUN --mount=type=cache,target=/root/.cache/uv \
    RECOMMENDED_PLUGINS=$(uv run python -c "\
from importlib.metadata import metadata; \
print(*(r[4:].split(';')[0].strip() \
for r in (metadata('eth-ape').get_all('Requires-Dist') or []) \
if 'recommended-plugins' in r))") && \
    ape plugins install $RECOMMENDED_PLUGINS

FROM ${SLIM_IMAGE}

WORKDIR /home/harambe

COPY --from=builder --chown=harambe:harambe /wheels/.venv /wheels/.venv

USER harambe

# Add the virtual environment to PATH so Ape is callable
ENV PATH="/wheels/.venv/bin:$PATH"
RUN ape --version
RUN ape plugins list

# NOTE: Don't override ENTRYPOINT
