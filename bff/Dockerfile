# syntax=docker/dockerfile:1

# ==============================================================================
# Standalone Backend-for-Frontend (BFF) & React UI Dockerfile
#
# Purpose: Packages the FastAPI BFF service along with the compiled React static 
#          frontend assets.
#
# Scope: Designed for deployment to Google Cloud Run in production/staging. When
#        deployed with AGENT_RUNTIME_ID set, this service routes agent queries
#        remotely to the standalone Agent Runtime container. It copies the
#        `agent/finops_agent` directory to resolve utility imports (such as logging
#        and telemetry configurations) but does not execute the cognitive loops.
# ==============================================================================

# ==========================================
# Stage 1: Build the React static frontend
# ==========================================
FROM node:20-slim AS frontend-builder

WORKDIR /app/frontend

# Copy package manifests first to leverage Docker layer caching for node_modules
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

# Copy the rest of the frontend source code and compile
COPY frontend/ ./
RUN npm run build

# ==========================================
# Stage 2: Final Backend Service Container
# ==========================================
FROM python:3.12-slim

# Install uv for fast, reliable Python package management.
RUN pip install --no-cache-dir uv==0.11.16

WORKDIR /code

# Copy dependency manifests and sync.
# We use synchronization flags to:
# 1. --frozen: Ensure the environment matches the lockfile.
# 2. --no-dev: Exclude testing/dev tools from the production image.
# 3. --no-install-project: Skip installing local packages until source is copied.
COPY ./pyproject.toml ./README.md ./uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy the BFF application code
COPY ./bff ./bff

# Copy the agent package (since BFF imports from it, e.g. for local fallback)
COPY ./agent/finops_agent ./agent/finops_agent

# Copy the built frontend static assets from Stage 1
COPY --from=frontend-builder /app/frontend/dist /code/frontend/dist

# Inject build-time metadata
ARG COMMIT_SHA=""
ENV COMMIT_SHA=${COMMIT_SHA}

ARG AGENT_VERSION=0.0.0
ENV AGENT_VERSION=${AGENT_VERSION}

# Create and switch to a non-root user for improved security (Principle of Least Privilege).
RUN useradd -m appuser
USER appuser

# Add the virtual environment's bin to PATH.
# We call uvicorn directly to avoid 'uv run' runtime sync checks, which 
# would otherwise fail on a cross-user/read-only .venv.
ENV PATH="/code/.venv/bin:$PATH"

EXPOSE 8080

CMD ["uvicorn", "bff.fast_api_app:app", "--host", "0.0.0.0", "--port", "8080"]
