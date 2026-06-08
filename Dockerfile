FROM ghcr.io/astral-sh/uv:bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed

# Install build dependencies
RUN apt-get update -y && \
    apt-get install --no-install-recommends -y git && \
    rm -rf /var/lib/apt/lists/*

# Install Python 3.13
RUN uv python install 3.13

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-install-project --no-dev
COPY . /app
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev

# Use Playwright's official Python image for the runtime
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble AS runtime

# Copy only necessary files from builder
COPY --from=builder /python /python
COPY --from=builder /app /app

ENV ANONYMIZED_TELEMETRY=false \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    BROWSER_USE_HEADLESS=true

WORKDIR /app

EXPOSE 8000

# Run the server directly
CMD ["python", "server", "--port", "8000"]
