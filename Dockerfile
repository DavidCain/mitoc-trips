# TODO:
# - Once dropping legacy AngularJS, build FE bundles separately

# Things needed to use this in production:
# - Direct logs to files outside the container
# - Define containers for Celery workers
# - Run Postgres in a container locally

FROM ubuntu:26.04 AS build

ENV DEBIAN_FRONTEND="noninteractive"
ENV UV_PYTHON_INSTALL_DIR="/opt/python"
# Use copy mode since the cache and build filesystem are on different volumes.
ENV UV_LINK_MODE=copy
ENV PYTHONUNBUFFERED=1
# https://docs.astral.sh/uv/guides/integration/docker/#compiling-bytecode
ENV UV_COMPILE_BYTECODE=1

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    gcc \
    locales \
    postgresql-client postgresql-contrib libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN locale-gen en_US.UTF-8
RUN update-locale en_US.UTF-8

ENV LANGUAGE=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

WORKDIR /app/

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
COPY .python-version .

# From both Astral & Docker guides, you shouldn't *have* to copy these...
COPY pyproject.toml .
COPY uv.lock .

# https://docs.astral.sh/uv/guides/integration/docker/#intermediate-layers-in-workspaces
# We do explicitly add `all-groups` so our image can be used in tests.
# (Production images will remove dev deps)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --all-groups --no-install-project

COPY manage.py .
COPY ws ./ws

RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --all-groups --locked

# ------------------------------------------------------------------------

FROM build AS ci

RUN WS_DJANGO_TEST=1 uv run manage.py collectstatic

# ------------------------------------------------------------------------

FROM build AS installer

# At present, production purposes read some secrets from env vars.
# However, there's no need for that to *only* collect static files.
RUN WS_DJANGO_LOCAL=1 uv run manage.py collectstatic

# Remove dev dependencies (smaller venv, no dev deps in prod)
RUN uv sync --no-dev

# ------------------------------------------------------------------------

# TODO: Consider alpine
FROM ubuntu:26.04 AS production

WORKDIR /app/
ENV PATH="/app/.venv/bin:$PATH"

# The venv symlinks its Python to the version that `uv` installs globally.
COPY --from=installer /opt/python /opt/python
# We now copy the venv which should have *only* production dependencies.
COPY --from=installer /app/.venv ./.venv

COPY ws ./ws
COPY entrypoint.sh ./

# Copy collected static files (JS bundles & more)
COPY --from=installer /app/static ./static

EXPOSE 8000
ENTRYPOINT ["./entrypoint.sh"]
