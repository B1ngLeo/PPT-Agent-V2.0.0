# syntax=docker/dockerfile:1.7
FROM ghcr.io/astral-sh/uv@sha256:e85be844203885286c60ffad8a858d48afb6c5a5c237ca0e67f12e74b8f174b1 AS uv
FROM python@sha256:a3e58f9399353be051735f09be0316bfdeab571a5c6a24fd78b92df85bcb2d85

COPY --from=uv /uv /uvx /bin/

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_DEV=1

RUN groupadd --gid 10001 instantppt \
    && useradd --uid 10001 --gid 10001 --create-home --shell /usr/sbin/nologin instantppt

WORKDIR /app
COPY pyproject.toml uv.lock .python-version ./
COPY packages/domain/pyproject.toml packages/domain/pyproject.toml
COPY services/api/pyproject.toml services/api/pyproject.toml
COPY services/worker/pyproject.toml services/worker/pyproject.toml
RUN uv sync --frozen --no-dev --package instant-ppt-api --no-install-workspace

COPY packages/domain/src packages/domain/src
COPY services/api/src services/api/src
RUN uv sync --frozen --no-dev --package instant-ppt-api --no-editable

USER 10001:10001
EXPOSE 8000
ENTRYPOINT ["uvicorn"]
CMD ["instant_ppt_api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "4"]
