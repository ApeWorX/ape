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
WORKDIR /wheels

# Only copy dependency files first (locked deps change less often)
# NOTE: In CI, you need to cache `uv.lock` (or create it if it doesn't exist)
COPY pyproject.toml uv.lock ./

# NOTE: Needed to mock version for `setuptools-scm` (pass at build time)
ARG APE_VERSION
ENV SETUPTOOLS_SCM_PRETEND_VERSION_FOR_ETH_APE=${APE_VERSION}

# NOTE: link mode "copy" silences warnings about hard links in other commands
ENV UV_LINK_MODE=copy

# Install dependencies first
# NOTE: --compile-bytecode improves load speed of dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --no-editable --compile-bytecode

# Now copy Ape's source code over
COPY src src

# Install Ape using pre-installed dependencies
# NOTE: --compile-bytecode improves load speed of dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable --compile-bytecode

# Stage 2: Slim image (ape core only)

FROM python:${PYTHON_VERSION}-slim AS slim

# NOTE: Add a bespoke user to run commands with
RUN useradd --create-home --shell /bin/bash harambe
WORKDIR /home/harambe

COPY --from=slim-builder --chown=harambe:harambe /wheels/.venv /wheels/.venv

# NOTE: Switch non-root user for additional security
USER harambe

# Add the virtual environment to PATH so Ape is callable
ENV PATH="/wheels/.venv/bin:$PATH"
RUN ape --version

ENTRYPOINT ["ape"]
CMD ["--help"]

# Stage 3: Add plugins on top of slim-builder

FROM slim-builder AS full-builder

# Install recommended plugins
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-editable --compile-bytecode --extra recommended-plugins

# Stage 4: Full image (slim with recommended plugins from full-builder)

FROM slim AS full

COPY --from=full-builder --chown=harambe:harambe /wheels/.venv /wheels/.venv

RUN ape plugins list

# NOTE: Use same ENTRYPOINT and CMD as slim
