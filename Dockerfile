# --- Builder Stage ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1

# Copy only dependency files first to leverage caching
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-install-project --no-dev

# --- Final Stage ---
# Use slim python image instead of heavy playwright image
FROM python:3.12-slim-bookworm AS final

WORKDIR /app
ENV PYTHONUNBUFFERED=1

# 1. Install system dependencies required for runtime (if any)
# Minimal deps for python/mysql, but NO browser deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 2. Install uv in final stage
COPY --from=builder /usr/local/bin/uv /usr/local/bin/uv

# 3. Copy dependency files form builder
COPY --from=builder /app/.venv /app/.venv

# 4. Set venv path
ENV PATH="/app/.venv/bin:$PATH"

# 5. Copy the rest of the application code
COPY . .

# Explicitly set the default command
CMD ["uv", "run", "main.py"]
