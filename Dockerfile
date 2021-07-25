# TODO:
# - Consider Ubuntu 20.04 once moving off Python 3.6
# - Once we drop direct MySQL access, consider python:3.6-slim
# - Once dropping legacy AngularJS, build FE bundles separately

# Things needed to use this in production:
# - Direct logs to files outside the container
# - Ensure that Celery works as well
# - Run WSGI with an ENTRYPOINT

FROM ubuntu:18.04 as build

WORKDIR /app/

ENV DEBIAN_FRONTEND="noninteractive"

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential gcc \
    # Only for installing node \
    curl \
    # Only needed to install legacy node dependencies from git \
    git \
    # TODO: Remove these once we no longer need to support direct MySQL access \
    mysql-client libmysqlclient-dev libssl-dev \
    locales \
    # Postgres client (for accessing RDS in production) \
    postgresql-client postgresql-contrib libpq-dev \
    # NOTE: python3.6 is not available on Ubuntu 20.04. Upgrade Python before moving to 22.04 LTS. \
    python3.6 python3-dev python3-pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Install node directly into the container we'll use for Django.
# This is only necessary while we're still serving the legacy frontend.
# Once we're on the new Vue setup, all we need to do is copy in the build bundle & webpack-stats.json
RUN curl -sL https://deb.nodesource.com/setup_12.x | bash -
RUN apt-get update && apt-get install --no-install-recommends -y nodejs

RUN locale-gen en_US.UTF-8
RUN update-locale en_US.UTF-8

# `click` (used by `black`) will error out without locales explicitly set
ENV LANGUAGE=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

RUN pip3 install --upgrade pip==21.2.1

# TODO: Check asdf's .tool-versions
RUN pip install poetry==1.1.7
COPY poetry.lock .

# Instruct poetry to create a venv in `.venv`, then auto-add it to path
RUN poetry config virtualenvs.in-project true
ENV PATH="/app/.venv/bin:$PATH"

COPY pyproject.toml .

# Janky hackage follows: make Poetry & Docker caching play nicely together.
# -------------------------------------------------------------------------
# Docker will cache a layer if it sees that pyproject.toml hasn't changed.
# We specify our dependencies in the `[tool.poetry]` section of `pyproject.toml`
# If dependencies haven't changed in '[tool.poetry]` (or in `poetry.lock`),
# we can use Docker layers to avoid re-installing deps due to unrelated file changes.
# Unrelated changes in `pyproject.toml` can come from editing other tools, or even just comments.
# Extract *just* the sections for Poetry, removing comments and applying a consistent format.
# Since Poetry's `content-hash` is a hashed dictionary, not the file itself, so this works!
RUN pip install toml  # No need to uninstall; poetry will overwrite anyway
RUN python3 -c 'import toml; toml.dump({"tool": {"poetry": toml.load("pyproject.toml")["tool"]["poetry"]}}, open("pyproject.toml", "w"))'
RUN poetry install --no-root

# Copy the *full* pyproject.toml, which has config for black, isort, pylint, mypy
COPY pyproject.toml .

# Install legacy frontend
COPY package.json package-lock.json ./
RUN npm ci

# Build the new Vue frontend, creating webpack-stats.json which Django will serve
COPY frontend ./frontend
RUN npm --prefix=frontend/ ci
RUN npm --prefix=frontend/ run build

COPY manage.py .
COPY ws ./ws

RUN WS_DJANGO_TEST=1 ./manage.py collectstatic

# ------------------------------------------------------------------------

FROM build as installer

# Remove dev dependencies (smaller venv, no dev deps in prod)
RUN poetry install --no-root --no-dev

FROM ubuntu:18.04

WORKDIR /app/
ENV PATH="/app/.venv/bin:$PATH"
COPY ws ./ws

# We now copy the venv which should have *only* production dependencies.
COPY --from=installer /app/.venv ./.venv
# TODO: Copy static files too (but only if still serving legacy FE)
# ENTRYPOINT = ...
