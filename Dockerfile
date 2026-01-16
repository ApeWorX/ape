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

# UV Configurations
# NOTE: use system python (better for our images, that inherit from `python:$VERSION`)
ENV UV_MANAGED_PYTHON=false
# NOTE: skip installing dev-only dependencies
ENV UV_NO_DEV=true
# NOTE: use `uv.lock` that we loaded into build
ENV UV_FROZEN=true
# NOTE: installs everything as non-editable (faster)
ENV UV_NO_EDITABLE=true
# NOTE: improves load speed of dependencies
ENV UV_COMPILE_BYTECODE=true
# NOTE: link mode "copy" silences warnings about hard links in other commands
ENV UV_LINK_MODE=copy

# Install dependencies first
# NOTE: --no-install-project so that we have our dependencies built first (speeds up incremental builds)
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --no-install-project

# NOTE: Needed to mock version for `setuptools-scm` (pass at build time)
ARG APE_VERSION
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ETH_APE=${APE_VERSION}

# Now copy Ape's source code over
COPY src src

# Install Ape using pre-installed dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync

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
    uv sync --extra recommended-plugins

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
