# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv
FROM python@sha256:a3e58f9399353be051735f09be0316bfdeab571a5c6a24fd78b92df85bcb2d85

ARG APP_BUILD_REVISION=dev-uncommitted
ARG RUNTIME_CONTRACT_VERSION=instant-ppt-runtime@v2

COPY --from=uv /uv /uvx /bin/

# Chromium-based visual review needs an actual CJK font on Linux. Without it,
# otherwise valid Chinese SVG text renders as tofu boxes and blocks publishing.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends fontconfig fonts-noto-cjk \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/app/.venv/bin:$PATH" \
    APP_BUILD_REVISION="${APP_BUILD_REVISION}" \
    RUNTIME_CONTRACT_VERSION="${RUNTIME_CONTRACT_VERSION}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

LABEL org.opencontainers.image.revision="${APP_BUILD_REVISION}" \
      io.instant-ppt.runtime-contract="${RUNTIME_CONTRACT_VERSION}"

RUN groupadd --gid 10001 instantppt \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin instantppt

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY packages/domain/pyproject.toml packages/domain/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/worker/pyproject.toml services/worker/pyproject.toml
RUN uv sync --frozen --no-dev --package instant-ppt-worker --no-install-workspace

COPY services/worker/src services/worker/src
COPY packages/domain/src packages/domain/src
COPY vendor/ppt-master vendor/ppt-master
RUN uv sync --frozen --no-dev --package instant-ppt-worker --no-editable \
    && .venv/bin/python vendor/ppt-master/scripts/attribution_guard.py \
    && mkdir -p /workspace \
    && chown 10001:10001 /workspace

USER 10001:10001
WORKDIR /workspace
ENTRYPOINT ["engine-adapter"]
CMD ["--help"]
