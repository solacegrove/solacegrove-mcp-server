# Build stage
FROM ghcr.io/astral-sh/uv:bookworm-slim AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_INSTALL_DIR=/python \
    UV_PYTHON_PREFERENCE=only-managed

# Install build tools for C extensions and pin Python version
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential && \
    rm -rf /var/lib/apt/lists/*

RUN uv python install 3.13

WORKDIR /app

# Copy dependency files first
COPY uv.lock pyproject.toml /app/

# Install dependencies (no mounts, as Railway does not support them)
RUN uv sync --frozen --no-install-project --no-dev

# Copy the rest of the application
COPY . /app

# Final sync
RUN uv sync --frozen --no-install-project --no-dev

# Runtime stage - Use the specific version recommended for Railway
FROM mcr.microsoft.com/playwright/python:v1.52.0-noble AS runtime

WORKDIR /app

# Copy only the necessary parts from builder
COPY --from=builder /python /python
COPY --from=builder /app /app

# Set environment variables
ENV ANONYMIZED_TELEMETRY=false \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    BROWSER_USE_HEADLESS=true \
    PORT=8000

# Railway will automatically assign a port to the PORT environment variable
# We expose it here for clarity
EXPOSE 8000

# Run the server directly, ensuring it listens on all interfaces (0.0.0.0)
# and uses the PORT environment variable provided by Railway
CMD ["sh", "-c", "python server --port ${PORT:-8000}"]
