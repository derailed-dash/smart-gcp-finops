# ==============================================================================
# FinSavant Developer Makefile
# Scope: Orchestrates frontend, BFF, agent, testing, deployment targets, etc.
#
# Note: The shell pipelines (using sed, grep, paste) are designed for GNU
#       utilities. On macOS, default BSD utilities may occasionally exhibit
#       different argument behaviors. Ensure you have GNU coreutils installed
#       if encountering command substitution syntax errors.
# ==============================================================================

.PHONY: help install playground local-backend run-frontend docker-build docker-run \
        deploy-cloud-run deploy-agent-runtime get-agent-runtime-id export-requirements \
        validate-env lint lint-fix test test-all test-ui eval eval-all tf-plan tf-apply

# /////////////////////////////////////////////////////////////////////////////
# Why: This variable is used to parse and load .env file variables in-memory.
#      The .env contents are sanitised and joined with pipe '|' delimiters,
#      which are then substituted with this 'newline' variable before being
#      evaluated via $(eval ...).
# WARNING: Do not remove the two empty lines below. GNU Make requires exactly
#          two empty lines inside a define block to represent a single newline.
define newline


endef
# /////////////////////////////////////////////////////////////////////////////

# Load environment variables from .env file if it exists, sanitising quotes, comments, and trailing spaces in-memory
ifneq (,$(wildcard .env))
    CLEAN_ENV := $(shell sed -e 's/[#].*//' -e 's/["\x27]//g' -e 's/[[:space:]]*$$//' -e 's/$$/|/' .env)
    $(eval $(subst |,$(newline),$(CLEAN_ENV)))
endif

# ==============================================================================
# Installation & Setup
# ==============================================================================

# Assign env variables if they are not already set
MIN_INSTANCES ?= 0
MEMORY ?= "2Gi"
OTEL_TO_CLOUD ?= true
AGENT_RUNTIME_ID ?= $(shell uv run python scripts/get-agent-runtime-id.py "$(GOOGLE_CLOUD_PROJECT)" "$(GOOGLE_CLOUD_REGION)" "$(SERVICE_NAME)-backend" 2>/dev/null || echo "")
# Determines whether the local unified container runs the agent locally (default, empty)
# or proxies queries to a remote Agent Runtime deployment.
# To test remote proxy mode locally: make docker-run DOCKER_AGENT_RUNTIME_ID=$$(AGENT_RUNTIME_ID)
DOCKER_AGENT_RUNTIME_ID ?=

.DEFAULT_GOAL := help

# Default log levels for development and production
DEV_LOG_LEVEL ?= DEBUG
PROD_LOG_LEVEL ?= INFO

# Display this help menu of all available targets
help:
	@uv run python scripts/makefile-help.py

# Install dependencies using uv and npm package managers
install:
	@command -v uv >/dev/null 2>&1 || { echo "uv is not installed. Installing uv..."; curl -LsSf https://astral.sh/uv/0.11.16/install.sh | sh; source $HOME/.local/bin/env; }
	uv sync
	cd frontend && npm install

# ==============================================================================
# Local Development Commands
# ==============================================================================

# Launch local ADK Web dev playground
playground:
	@echo "==============================================================================="
	@echo "| 🚀 Starting your agent playground...                                        |"
	@echo "==============================================================================="
	uv run adk web agent/finops_agent --port 8501 --reload_agents

# Launch local development server with hot-reload
# Usage: make local-backend [PORT=8000] - Specify PORT for parallel scenario testing
local-backend:
	PYTHONPATH=agent uv run uvicorn bff.fast_api_app:app --host 127.0.0.1 --port $(or $(PORT),8000) --reload


# Launch the Vite Dev Server for the React UI
run-frontend:
	cd frontend && npm run dev

# ==============================================================================
# Unified Container Targets
# ==============================================================================

# Build the unified dev/production container locally
docker-build:
	docker build -t smart-gcp-finops:latest .

# Run the unified container locally, securely mounting local Google Application Default Credentials (ADC)
# and mapping all custom GCP FinOps environment variables.
# By default, runs in local fallback mode. To proxy to the remote Agent Runtime:
#   make docker-run DOCKER_AGENT_RUNTIME_ID=$(AGENT_RUNTIME_ID)
docker-run:
	docker run --rm -p 8080:8080 \
		-e GOOGLE_CLOUD_PROJECT="$(GOOGLE_CLOUD_PROJECT)" \
		-e GOOGLE_CLOUD_REGION="$(GOOGLE_CLOUD_REGION)" \
		-e GOOGLE_CLOUD_LOCATION="$(GOOGLE_CLOUD_LOCATION)" \
		-e GOOGLE_CLOUD_BILLING_ACCOUNT="$(GOOGLE_CLOUD_BILLING_ACCOUNT)" \
		-e GOOGLE_CLOUD_BILLING_LOCATION="$(GOOGLE_CLOUD_BILLING_LOCATION)" \
		-e GOOGLE_CLOUD_BILLING_PROJECT="$(GOOGLE_CLOUD_BILLING_PROJECT)" \
		-e BILLING_EXPORT_DATASET="$(BILLING_EXPORT_DATASET)" \
		-e GOOGLE_GENAI_USE_VERTEXAI="$(GOOGLE_GENAI_USE_VERTEXAI)" \
		-e MODEL="$(MODEL)" \
		-e FAST_MODEL="$(FAST_MODEL)" \
		-e GOOGLE_CLOUD_ORGANIZATION="$(GOOGLE_CLOUD_ORGANIZATION)" \
		-e LOGS_BUCKET_NAME="$(GOOGLE_CLOUD_PROJECT)-$(SERVICE_NAME)-logs" \
		-e LOG_LEVEL="$(DEV_LOG_LEVEL)" \
		-e AGENT_RUNTIME_ID="$(DOCKER_AGENT_RUNTIME_ID)" \
		-e LOCAL_DEVELOPER_EMAIL="$(LOCAL_DEVELOPER_EMAIL)" \
		-e COMMIT_SHA="$(shell git rev-parse HEAD 2>/dev/null || echo '')" \
		-e GOOGLE_APPLICATION_CREDENTIALS="/code/application_default_credentials.json" \
		--mount type=bind,source=$${HOME}/.config/gcloud/application_default_credentials.json,target=/code/application_default_credentials.json,readonly \
		smart-gcp-finops:latest
		
# ==============================================================================
# Backend Deployment Targets
# ==============================================================================

# Define the fully-qualified Artifact Registry image name
IMAGE_TAG = $(GOOGLE_CLOUD_REGION)-docker.pkg.dev/$(CICD_PROJECT_ID)/smart-gcp-finops-repo/smart-gcp-finops:latest

# Deploy the Backend-for-Frontend (BFF) & React UI container to Google Cloud Run.
# Note: This target builds the container using `bff/Dockerfile` (the standalone BFF+UI image, 
#       which executes as a remote proxy client to the Agent Runtime), and deploys it to Cloud Run.
#       It resolves the newest AGENT_RUNTIME_ID dynamically, packaging it as an env var on Cloud Run.
#       You MUST run this command after any backend updates deployed via `make deploy-agent-runtime` to update the BFF routing.
# WARNING: DO NOT use commas (,) in any environment variable values in `agent/.env` to avoid syntax errors.
deploy-cloud-run: validate-env
	@echo "🚀 Building and pushing standalone BFF+UI container (using bff/Dockerfile) to Artifact Registry..."
	gcloud builds submit --config deployment/cloudbuild-bff.yaml --substitutions="_IMAGE_TAG=$(IMAGE_TAG),_COMMIT_SHA=$(shell git rev-parse HEAD 2>/dev/null || echo '')" --project "$(CICD_PROJECT_ID)" .
	@echo "📦 Deploying BFF+UI image from Artifact Registry to Cloud Run..."
	gcloud run deploy "$(SERVICE_NAME)" \
		--image "$(IMAGE_TAG)" \
		--memory "$(MEMORY)" \
		--project "$(GOOGLE_CLOUD_PROJECT)" \
		--region "$(GOOGLE_CLOUD_REGION)" \
		--service-account "$(SERVICE_SA_EMAIL)" \
		--max-instances=1 \
		--min-instances=$(MIN_INSTANCES) \
		--cpu-boost \
		--no-allow-unauthenticated \
		--iap \
		--update-env-vars="$$(grep -v '^#' agent/.env | grep -v '^$$' | sed -e 's/^export //g' -e 's/["\x27]//g' | paste -sd, -),LOG_LEVEL=$(PROD_LOG_LEVEL),AGENT_RUNTIME_ID=$(AGENT_RUNTIME_ID),COMMIT_SHA=$(shell git rev-parse HEAD)"

# Deploy the standalone ADK agent (packaged via agent/Dockerfile) to Gemini Enterprise Agent Runtime.
# Note: Deploys the Python agent logic (in `agent/`) to create a new Reasoning Engine ID.
# After this finishes, you MUST redeploy the Cloud Run service (`make deploy-cloud-run`) to update BFF routing to this new instance.
deploy-agent-runtime: validate-env
	cd agent && uvx google-agents-cli deploy \
		--deployment-target agent_runtime \
		--no-confirm-project \
		--project "$(GOOGLE_CLOUD_PROJECT)" \
		--region "$(GOOGLE_CLOUD_REGION)" \
		--service-account "$(SERVICE_SA_EMAIL)" \
		--service-name "$(SERVICE_NAME)-backend" \
		--min-instances 0 \
		--max-instances 1 \
		--update-env-vars="$$(grep -v '^#' .env | grep -v '^$$' | grep -v 'GOOGLE_CLOUD_PROJECT' | sed -e 's/^export //g' -e 's/["\x27]//g' | paste -sd, -),LOG_LEVEL=$(PROD_LOG_LEVEL)"

# Retrieve the deployed agent runtime ID (Reasoning Engine resource name)
get-agent-runtime-id:
	@uv run python scripts/get-agent-runtime-id.py "$(GOOGLE_CLOUD_PROJECT)" "$(GOOGLE_CLOUD_REGION)" "$(SERVICE_NAME)-backend"

# Compile requirements.txt inside the agent package.
# Why: Vertex AI SDK requires a standard requirements.txt for Reasoning Engine packaging.
# Note: Developers must NOT edit requirements.txt manually. Add dependencies to agent/pyproject.toml and run this target.
export-requirements:
	uv pip compile agent/pyproject.toml -o agent/finops_agent/requirements.txt

# Validate that no environment variables in agent/.env contain forbidden comma characters.
validate-env:
	@if grep -v '^#' agent/.env | grep -q ','; then \
		echo "❌ Error: agent/.env contains a comma (,) which is forbidden in Cloud Run environment variables."; \
		exit 1; \
	fi

# ==============================================================================
# Testing & Code Quality
# ==============================================================================

# Run code quality checks (codespell, ruff, ty)
lint:
	uv sync --dev --extra lint
	uv run codespell
	uv run ruff check . --diff
	uv run ruff format . --check --diff
	uv run ty check agent/

# Automatically fix code quality issues (codespell write, ruff check fix, ruff format)
lint-fix:
	uv sync --dev --extra lint
	uv run codespell -w
	uv run ruff check . --fix
	uv run ruff format .

# Run unit tests
test:
	uv sync --dev
	uv run pytest tests/unit

# Run unit and integration tests
test-all:
	uv sync --dev
	uv run pytest tests/unit && uv run pytest tests/integration

# Run frontend checks (TypeScript type-checking and ESLint)
test-ui:
	cd frontend && npm run lint && npm run build

# ==============================================================================
# Agent Evaluation
# ==============================================================================

# Run agent evaluation using ADK eval
# Usage: make eval [EVALSET=tests/eval/evalsets/basic.evalset.json] [EVAL_CONFIG=tests/eval/eval_config.json]
eval:
	@echo "==============================================================================="
	@echo "| Running Agent Evaluation                                                    |"
	@echo "==============================================================================="
	uv sync --dev --extra eval
	uv run adk eval ./agent $${EVALSET:-tests/eval/evalsets/basic.evalset.json} \
		$(if $(EVAL_CONFIG),--config_file_path=$(EVAL_CONFIG),$(if $(wildcard tests/eval/eval_config.json),--config_file_path=tests/eval/eval_config.json,))

# Run evaluation with all evalsets
eval-all:
	@echo "==============================================================================="
	@echo "| Running All Evalsets                                                        |"
	@echo "==============================================================================="
	@for evalset in tests/eval/evalsets/*.evalset.json; do \
		echo ""; \
		echo "▶ Running: $$evalset"; \
		$(MAKE) eval EVALSET=$$evalset || exit 1; \
	done
	@echo ""
	@echo "✅ All evalsets completed"

# ==============================================================================
# Terraform
# ==============================================================================

# Run Terraform Plan
tf-plan:
	(cd deployment/terraform && terraform init && GITHUB_TOKEN="$(GITHUB_TOKEN)" terraform plan --var-file vars/env.tfvars)

# Run Terraform Apply (and auto-approve)
tf-apply:
	(cd deployment/terraform && terraform init && GITHUB_TOKEN="$(GITHUB_TOKEN)" terraform apply --var-file vars/env.tfvars --auto-approve)
