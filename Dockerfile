# syntax=docker/dockerfile:1.7
ARG PYTHON_IMAGE=python:3.12-slim
ARG UV_VERSION=0.9.0

# ---------- uv: binary source only ----------
FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

# ---------- base: shared foundation for build and runtime ----------
FROM ${PYTHON_IMAGE} AS base
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1
WORKDIR /app

# ---------- deps: external dependencies, cached separately from source code ----------
FROM base AS deps
COPY --from=uv /uv /uvx /bin/
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
ARG SERVICE
RUN test -n "$SERVICE" || (echo "Missing --build-arg SERVICE (router|notifier)" >&2 && exit 1)

# Copy manifests only: source code changes won't invalidate this layer
COPY pyproject.toml uv.lock ./
COPY libs/common/pyproject.toml libs/common/
COPY services/router/pyproject.toml services/router/
COPY services/notifier/pyproject.toml services/notifier/
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package "${SERVICE}" --no-install-workspace

# ---------- builder: workspace source code, installed as regular packages ----------
FROM deps AS builder
ARG SERVICE
COPY libs/common libs/common
COPY services/${SERVICE} services/${SERVICE}
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package "${SERVICE}" --no-editable

# ---------- test: full development environment, using the same versions as uv.lock ----------
FROM deps AS test
COPY . .
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-packages
CMD ["uv", "run", "--frozen", "--no-sync", "pytest", "--cov"]

# ---------- runtime: tylko Python + .venv ----------
FROM base AS runtime
ARG SERVICE
ENV SERVICE=${SERVICE} \
    PORT=8000 \
    PATH="/app/.venv/bin:${PATH}"
RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --no-create-home --shell /usr/sbin/nologin app \
    && mkdir -p /data && chown app:app /data
COPY --from=builder /app/.venv /app/.venv
COPY --chmod=0755 docker/entrypoint.sh /usr/local/bin/entrypoint
USER app
EXPOSE 8000
ENTRYPOINT ["entrypoint"]
CMD ["api"]
