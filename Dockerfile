#----------------------------------------------------------#
# See LICENSE in the project root for license information. #
#----------------------------------------------------------#
ARG PYTHON_VERSION="3.11"
ARG APE_VERSION

# Stage 1: Build dependencies

# Start with given Python version
# NOTE: use full so it has necessary compilers
FROM python:${PYTHON_VERSION} AS slim-builder

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/

# Change the working directory to a temp directory for building wheels
# NOTE: **Must** use our final workdir or else the hash bangs in the scripts don't work
WORKDIR /home/harambe/project

# Only copy dependency files first (locked deps change less often)
# NOTE: In CI, you need to cache `uv.lock` (or create it if it doesn't exist)
COPY pyproject.toml uv.lock ./

# NOTE: link mode "copy" silences warnings about hard links in other commands
ENV UV_LINK_MODE=copy

# Install dependencies first
# --no-managed-python to use system python
# --no-dev to skip installing dev-only dependencies
# --frozen to use `uv.lock` (that we loaded before)
# --no-editable installs everything as non-edtiable (faster)
# --compile-bytecode improves load speed of dependencies
# --no-install-project so that we have our dependencies built first (speeds up incremental builds)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --no-managed-python \
        --no-dev \
        --frozen \
        --no-editable \
        --compile-bytecode \
        --no-install-project

# NOTE: Needed to mock version for `setuptools-scm` (pass at build time)
ARG APE_VERSION
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ETH_APE=${APE_VERSION}

# Now copy Ape's source code over
COPY src src

# Install Ape using pre-installed dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --no-managed-python \
        --no-dev \
        --frozen \
        --no-editable \
        --compile-bytecode

# Stage 2: Slim image (ape core only)

FROM python:${PYTHON_VERSION}-slim AS slim

# NOTE: Add a bespoke user to run commands with
RUN useradd --create-home --shell /bin/bash harambe
WORKDIR /home/harambe/project

COPY --from=slim-builder --chown=harambe:harambe \
    /home/harambe/project/.venv /home/harambe/project/.venv

# NOTE: Switch non-root user for additional security
USER harambe

# Add the virtual environment to PATH so Ape is callable
ENV PATH="/home/harambe/project/.venv/bin:$PATH"
RUN ape --version

ENTRYPOINT ["ape"]
CMD ["--help"]

# Stage 3: Add plugins on top of slim-builder

FROM slim-builder AS full-builder

# Install recommended plugins
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync \
        --no-managed-python \
        --no-dev \
        --frozen \
        --no-editable \
        --compile-bytecode \
        --extra recommended-plugins

# Stage 4: Full image (slim with recommended plugins from full-builder)

FROM slim AS full

# Install anvil (for the Foundry plugin to be useful)
# NOTE: Adds 33MB to build
COPY --from=ghcr.io/foundry-rs/foundry:stable \
    /usr/local/bin/anvil /home/harambe/.local/bin/anvil

COPY --from=full-builder --chown=harambe:harambe \
    /home/harambe/project/.venv /home/harambe/project/.venv

RUN ape plugins list

# NOTE: Use same WORKDIR, USER, ENTRYPOINT and CMD as slim
