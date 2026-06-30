# Load environment variables from .env file if it exists
ifneq (,$(wildcard .env))
    include .env
    export
endif

# ==============================================================================
# Installation & Setup
# ==============================================================================

# Assign env variables if they are not already set
MIN_INSTANCES ?= 0
MEMORY ?= "2Gi"
OTEL_TO_CLOUD ?= true

# Default log levels for development and production if not already defined (e.g. in .env)
DEV_LOG_LEVEL = $(or $(LOG_LEVEL),DEBUG)
PROD_LOG_LEVEL = $(or $(LOG_LEVEL),INFO)

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
	@echo "|                                                                             |"
	@echo "| 💡 Try asking: What's the weather in San Francisco?                         |"
	@echo "|                                                                             |"
	@echo "| 🔍 IMPORTANT: Select the 'app' folder to interact with your agent.          |"
	@echo "==============================================================================="
	uv run adk web . --port 8501 --reload_agents

# Launch local development server with hot-reload
# Usage: make local-backend [PORT=8000] - Specify PORT for parallel scenario testing
local-backend:
	uv run uvicorn app.fast_api_app:app --host localhost --port $(or $(PORT),8000) --reload

# Run the Backend BFF Server (FastAPI + ADK Agent)
run-backend:
	uv run python -m app.fast_api_app

# Launch the Vite Dev Server for the React UI
run-frontend:
	cd frontend && npm run dev

# ==============================================================================
# Unified Container Targets
# ==============================================================================

# Build the unified dev/production container locally
build: docker-build

docker-build:
	docker build -t smart-gcp-finops:latest .

# Shortcut for running the unified container locally
run: docker-run

# Run the unified container locally, securely mounting local Google Application Default Credentials (ADC)
# and mapping all custom GCP FinOps environment variables.
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
		-e AGENT_RUNTIME_ID="$(AGENT_RUNTIME_ID)" \
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

# Deploy the agent to Cloud Run
# Usage: make deploy [IAP=true] [PORT=8080] - Set IAP=true to enable Identity-Aware Proxy, PORT to specify container port
deploy-cloud-run:
	@echo "🚀 Building and pushing container to Artifact Registry..."
	gcloud builds submit --tag "$(IMAGE_TAG)" --project "$(CICD_PROJECT_ID)" .
	@echo "📦 Deploying image from Artifact Registry to Cloud Run..."
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
		--set-env-vars="GOOGLE_CLOUD_PROJECT=$(GOOGLE_CLOUD_PROJECT),GOOGLE_CLOUD_REGION=$(GOOGLE_CLOUD_REGION),GOOGLE_CLOUD_LOCATION=$(GOOGLE_CLOUD_LOCATION),GOOGLE_CLOUD_BILLING_ACCOUNT=$(GOOGLE_CLOUD_BILLING_ACCOUNT),GOOGLE_CLOUD_BILLING_LOCATION=$(GOOGLE_CLOUD_BILLING_LOCATION),GOOGLE_CLOUD_BILLING_PROJECT=$(GOOGLE_CLOUD_BILLING_PROJECT),BILLING_EXPORT_DATASET=$(BILLING_EXPORT_DATASET),GOOGLE_GENAI_USE_VERTEXAI=$(GOOGLE_GENAI_USE_VERTEXAI),MODEL=$(MODEL),FAST_MODEL=$(FAST_MODEL),GOOGLE_CLOUD_ORGANIZATION=$(GOOGLE_CLOUD_ORGANIZATION),LOGS_BUCKET_NAME=$(GOOGLE_CLOUD_PROJECT)-$(SERVICE_NAME)-logs,COMMIT_SHA=$(shell git rev-parse HEAD),LOG_LEVEL=$(PROD_LOG_LEVEL)"

# Deploy the agent backend to Gemini Enterprise Agent Runtime
deploy-agent-runtime: export-requirements
	uvx google-agents-cli deploy \
		--deployment-target agent_runtime \
		--no-confirm-project \
		--project "$(GOOGLE_CLOUD_PROJECT)" \
		--region "$(GOOGLE_CLOUD_REGION)" \
		--service-account "$(SERVICE_SA_EMAIL)" \
		--service-name "$(SERVICE_NAME)-backend" \
		--update-env-vars="GOOGLE_CLOUD_REGION=$(GOOGLE_CLOUD_REGION),GOOGLE_CLOUD_LOCATION=$(GOOGLE_CLOUD_LOCATION),GOOGLE_CLOUD_BILLING_ACCOUNT=$(GOOGLE_CLOUD_BILLING_ACCOUNT),GOOGLE_CLOUD_BILLING_LOCATION=$(GOOGLE_CLOUD_BILLING_LOCATION),GOOGLE_CLOUD_BILLING_PROJECT=$(GOOGLE_CLOUD_BILLING_PROJECT),BILLING_EXPORT_DATASET=$(BILLING_EXPORT_DATASET),GOOGLE_GENAI_USE_VERTEXAI=$(GOOGLE_GENAI_USE_VERTEXAI),MODEL=$(MODEL),FAST_MODEL=$(FAST_MODEL),GOOGLE_CLOUD_ORGANIZATION=$(GOOGLE_CLOUD_ORGANIZATION),LOGS_BUCKET_NAME=$(GOOGLE_CLOUD_PROJECT)-$(SERVICE_NAME)-logs,OTEL_TO_CLOUD=$(OTEL_TO_CLOUD),LOG_LEVEL=$(PROD_LOG_LEVEL)"

# Retrieve the deployed agent runtime ID (Reasoning Engine resource name)
get-agent-runtime-id:
	@uv run python scripts/get-agent-runtime-id.py "$(GOOGLE_CLOUD_PROJECT)" "$(GOOGLE_CLOUD_REGION)" "$(SERVICE_NAME)-backend"

export-requirements:
	uv pip compile pyproject.toml -o app/app_utils/.requirements.txt

# ==============================================================================
# Testing & Code Quality
# ==============================================================================

# Run unit tests
test:
	uv sync --dev
	uv run pytest tests/unit

# Run all tests (unit and integration)
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
	uv run adk eval ./app $${EVALSET:-tests/eval/evalsets/basic.evalset.json} \
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

# Run code quality checks (codespell, ruff, ty)
lint:
	uv sync --dev --extra lint
	uv run codespell
	uv run ruff check . --diff
	uv run ruff format . --check --diff
	uv run ty check app/

# Set up development environment resources using Terraform
tf-plan:
	(cd deployment/terraform && terraform init && terraform plan --var-file vars/env.tfvars)

tf-apply:
	(cd deployment/terraform && terraform init && terraform apply --var-file vars/env.tfvars --auto-approve)
