# Build stage
FROM ghcr.io/astral-sh/uv:bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed

WORKDIR /app

# Copy dependency files first
COPY uv.lock pyproject.toml /app/

# Install dependencies (no mounts)
RUN uv sync --frozen --no-install-project --no-dev

# Copy the rest of the application
COPY . /app

# Final sync
RUN uv sync --frozen --no-dev

# Runtime stage
FROM mcr.microsoft.com/playwright/python:v1.50.0-noble AS runtime

WORKDIR /app

# Copy from builder
COPY --from=builder /python /python
COPY --from=builder /app /app

ENV ANONYMIZED_TELEMETRY=false \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    BROWSER_USE_HEADLESS=true \
    PORT=8000

EXPOSE 8000

# Run the server directly
CMD ["python", "server", "--port", "8000"]
