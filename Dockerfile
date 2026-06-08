FROM ghcr.io/astral-sh/uv:bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed

RUN apt-get update -y && \
    apt-get install --no-install-recommends -y git && \
    rm -rf /var/lib/apt/lists/*

RUN uv python install 3.13

WORKDIR /app
COPY uv.lock pyproject.toml ./
RUN uv sync --frozen --no-install-project --no-dev
COPY . /app
RUN uv sync --frozen --no-dev --no-install-project

FROM mcr.microsoft.com/playwright/python:v1.50.0-noble AS runtime

COPY --from=builder /python /python
COPY --from=builder /app /app

ENV ANONYMIZED_TELEMETRY=false \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    BROWSER_USE_HEADLESS=true

WORKDIR /app

EXPOSE 8000

CMD ["python", "server", "--port", "8000"]
