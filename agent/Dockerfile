FROM python:3.12-slim

RUN pip install --no-cache-dir uv==0.11.16

WORKDIR /code

COPY ./pyproject.toml ./README.md ./uv.lock* ./

COPY ./finops_agent ./finops_agent

RUN uv sync --frozen

ENV PATH="/code/.venv/bin:$PATH"

ARG COMMIT_SHA=""
ENV COMMIT_SHA=${COMMIT_SHA}

ARG AGENT_VERSION=0.0.0
ENV AGENT_VERSION=${AGENT_VERSION}

EXPOSE 8080
CMD ["python", "-m", "google.adk.cli", "api_server", "--host", "0.0.0.0", "--port", "8080", "--gemini_enterprise_app_name", "finops_agent"]