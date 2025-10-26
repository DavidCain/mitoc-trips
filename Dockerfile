# TODO:
# - Consider python:3.10-slim
# - Once dropping legacy AngularJS, build FE bundles separately

# Things needed to use this in production:
# - Direct logs to files outside the container
# - Ensure that Celery works as well
# - Run WSGI with an ENTRYPOINT

FROM ubuntu:22.04 AS build

WORKDIR /app/

ENV DEBIAN_FRONTEND="noninteractive"

RUN apt-get update && apt-get install --no-install-recommends -y \
    build-essential \
    gcc \
    locales \
    # Postgres client (for accessing RDS in production) \
    postgresql-client postgresql-contrib libpq-dev \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

RUN locale-gen en_US.UTF-8
RUN update-locale en_US.UTF-8

ENV LANGUAGE=en_US.UTF-8
ENV LANG=en_US.UTF-8
ENV LC_ALL=en_US.UTF-8

COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/
COPY pyproject.toml .
RUN uv sync --all-groups

# TODO: We should install & build the legacy frontend here.
# But I'm likely going to just rebuild everything. See the Git log for more.

COPY manage.py .
COPY ws ./ws

# NOTE: For the legacy AngularJS build, setting `WS_DJANGO_TEST` bypasses compressors
# (yuglify, specifically). Not a problem for tests, but does break production.
# Hopefully we've dropped the legacy setup & can just use webpack.
RUN WS_DJANGO_TEST=1 uv run manage.py collectstatic

# ------------------------------------------------------------------------

FROM build AS installer

# Remove dev dependencies (smaller venv, no dev deps in prod)
RUN uv sync --no-dev

FROM ubuntu:22.04

WORKDIR /app/
ENV PATH="/app/.venv/bin:$PATH"
COPY ws ./ws

# We now copy the venv which should have *only* production dependencies.
COPY --from=installer /app/.venv ./.venv
# TODO: Copy static files too (but only if still serving legacy FE)
# ENTRYPOINT = ...
