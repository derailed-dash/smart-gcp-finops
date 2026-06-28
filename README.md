# FinSavant: Dazbo's Google Cloud FinOps Intelligence

An agentic FinOps solution for Google Cloud Platform (GCP) created by [Dazbo](https://dazbo.co.uk) that empowers Cloud Platform Engineers and FinOps Practitioners to manage, understand, and optimise cloud spend across their entire organization.

![FinSavant](docs/images/finsavant-explain-spike.png)

## Features

- **BigQuery Billing Integration**: Direct access to BigQuery billing exports for cross-project cost analysis.
- **BigQuery ADK Integration**: Native dataset and table schema awareness using ADK's native `BigQueryToolset` with local query caching.
- **Natural Language Chat Interface**: A React-based UI allowing users to query billing data and infrastructure state in plain English.
- **FinOps Dashboard**: A centralized view for cost trends, anomaly reports, and optimization progress.
- **Zombie Resource Detection & Audit**: Proactively identifies cost waste such as unattached persistent disks using Cloud Asset Inventory. Correlates billing spikes with historical configuration changes.
- **Multi-Project Analysis**: Ability to scope analysis to specific projects, billing accounts, or the entire Google Cloud Organization.
- **AI-powered Forecasting**: Predict future cloud consumption and budget requirements using historical data.
- **Automated Anomaly Detection**: Proactively identify unusual billing spikes and cost inefficiencies.
- **Actionable Recommendations**: Combine billing insights with architectural best practices for high-impact cost optimization.

## Target Audience

- **Cloud Platform Engineers**: Managing infrastructure and resource lifecycle.
- **FinOps Practitioners**: Dedicated teams responsible for cloud financial governance.
- **GCP Organization Admins**: Overseeing cost and compliance across a large-scale cloud footprint.

## Success Metrics

- **Spend Reduction %**: Target reduction in unoptimized spend.
- **Anomaly Detection Speed**: Minimize MTTD (Mean Time to Detect) for billing outliers.
- **Forecasting Accuracy**: High precision in projected budget versus actual realization.

## Project Structure

```
smart-gcp-finops/
├── app/               # Core agent code (FastAPI + ADK)
│   ├── agent.py               # Main agent logic
│   ├── fast_api_app.py        # FastAPI Backend for Frontend
│   └── app_utils/             # App utilities and helpers
├── deployment/        # Infrastructure and CI/CD (Terraform)
│   └── terraform/             # Centralized IaC for Prod & Staging
├── docs/              # System-wide architecture and design documentation
│   ├── images/                # Diagrams and architectural visual assets
│   ├── DESIGN.md              # Visual identity, components, and design tokens
│   ├── architecture-and-walkthrough.md # Solution blueprints, ADRs, and component data flows
│   └── testing.md             # Testing strategy and verification instructions
├── notebooks/         # Jupyter notebooks for prototyping and evaluation
│   └── adk_app_testing.ipynb  # Interactive playground for testing local and remote runs
├── tests/             # Unit and integration tests
├── .gemini/           # Gemini CLI configuration (MCP settings)
├── GEMINI.md          # Context for the Antigravity/Gemini AI development assistant
├── Makefile           # Development commands
└── pyproject.toml     # Project dependencies (Python 3.12, uv)
```

## Requirements

Before you begin, ensure you have:
- **uv**: Python package manager (Python 3.12+)
- **Google Cloud SDK**: Authenticated with your GCP project
- **Terraform**: For infrastructure deployment
- **make**: Build automation tool

## Quick Start

Install required packages and launch the local development environment:

```bash
make install && make playground
```

## Commands

| Command              | Description                                                       |
| -------------------- | ----------------------------------------------------------------- |
| `make install`       | Install dependencies using `uv`                                   |
| `make playground`    | Launch local development environment (ADK Dev UI)                 |
| `make run-backend`   | Run the Backend BFF Server locally (runs agent locally unless `AGENT_RUNTIME_ID` is set) |
| `make run-frontend`  | Launch the Vite Dev Server for the React UI                       |
| `make lint`          | Run backend code quality checks (`ruff`, `codespell`, `ty`)       |
| `make test-ui`       | Run frontend compiler and lint checks (TypeScript, ESLint)        |
| `make test`          | Run unit and integration tests (`pytest`)                         |
| `make build`         | Shortcut to build the unified production container image locally    |
| `make docker-build`  | Build the unified production container image (React + FastAPI) locally |
| `make docker-run`    | Run the built container locally (runs agent locally unless `AGENT_RUNTIME_ID` is set) |
| `make run`           | Shortcut for `make docker-run` to run the container locally        |
| `make tf-plan`       | Initialize Terraform and plan infrastructure deployment           |
| `make tf-apply`      | Initialize Terraform and apply deployment configuration           |
| `make deploy-agent-runtime` | Deploy backend agent code to Gemini Enterprise Agent Runtime   |
| `make get-agent-runtime-id` | Retrieve the deployed Agent Runtime ID (resource URN)              |
| `make deploy-cloud-run` | Deploy BFF container to Cloud Run using Cloud Build              |


## Local Development & Testing Flow

The application can be run locally in two different ways:
1. **Standalone Services** (recommended for active development): Runs the React frontend and FastAPI backend as separate, hot-reloading processes.
2. **Unified Docker Container**: Runs the entire application (compiled React assets + FastAPI backend) inside a single local Docker container, replicating the production environment.

### Run as Standalone Services (Hot-Reloading)

To run the React frontend and FastAPI backend locally as standalone services, follow this developer workflow:

### Step 1: Initialise Dependencies

Install both the backend Python package dependencies (`uv sync`) and the React frontend package dependencies (`npm install`) automatically in one step:
```bash
make install
```

### Step 2: Run the Application

You will need two separate terminal sessions to run both servers concurrently with hot-reloading:

*   **Terminal 1 (Backend)**: Spin up the FastAPI Backend BFF on `http://localhost:8000`:
    ```bash
    make run-backend
    ```
*   **Terminal 2 (Frontend)**: Spin up the Vite dev server on `http://localhost:5173`:
    ```bash
    make run-frontend
    ```
Open your browser and navigate to `http://localhost:5173`. The frontend automatically proxies all `/api` and `/events` queries to the backend.

### Run as a Single Docker Container

Alternatively, you can run the entire unified container (which bundles both the compiled React frontend and the FastAPI backend) locally using Docker:

```bash
# Build the unified container image locally
make docker-build

# Run the container locally (runs the agent locally unless AGENT_RUNTIME_ID is configured)
make docker-run
```
This launches the application on `http://localhost:8000`, running exactly as it would on Cloud Run.

### Step 3: Run Tests & Quality Gates
Before committing any changes to git, verify both the backend and frontend are healthy:

*   **Backend Linting & Types**: Run `ruff` linting/formatting and `ty` static typing checks:
    ```bash
    make lint
    ```
*   **Frontend Linting & Compile**: Run `eslint` checks and compile the production bundle to verify zero TypeScript errors:
    ```bash
    make test-ui
    ```
*   **Unit & Integration Tests**: Execute backend pytest coverage checks:
    ```bash
    make test
    ```

### Interactive Notebook Prototyping

An interactive notebook is available at [adk_app_testing.ipynb](notebooks/adk_app_testing.ipynb) for testing the agent in a sandbox environment. This allows:
- **Local Testing**: Instantiating the agent logic locally within the project virtual environment.
- **Remote Testing (Agent Runtime)**: Interacting with the deployed Gemini Enterprise Agent Runtime.
- **Remote Testing (Cloud Run)**: Triggering the deployed uvicorn server/SSE streaming interface.

For full usage instructions, refer to the [Testing Guide](docs/testing.md#interactive-testing-via-jupyter-notebook).

## CI/CD & Deployment Flow

FinSavant utilizes a decoupled GitHub Actions pipeline to enforce a strict quality gate before releasing code to Production. The architecture splits the application into two deployed targets:
1. **Agent Logic (Gemini Enterprise Agent Runtime)**: Managed serverless environment hosting the agent's Python code, callbacks, and tools.
2. **BFF + UI (Cloud Run)**: A lightweight container hosting the static React assets and a FastAPI thin proxy layer.

### GitHub Actions Pipelines

* **Continuous Integration (Staging)**: 
  - **Trigger**: Automatic on pushes or merges to the `main` branch. (Pull requests against branches only run linting, unit, and integration tests to ensure code health, but do not deploy anything to GCP).
  - **Actions**: The [.github/workflows/staging.yaml](.github/workflows/staging.yaml) workflow automatically packages and deploys the agent logic to the staging Agent Runtime (`finops-admin-dev`), extracts the resulting `AGENT_RUNTIME_ID`, builds the unified container image, and deploys it to the Staging Cloud Run BFF with the correct engine ID.
* **Verification**: Verify the staging environment to ensure all agent tools, BigQuery MCP connections, and React component renders function correctly.
* **Manual Gate (Production)**: 
  - **Trigger**: Manual trigger ("workflow dispatch") in GitHub Actions.
  - **Actions**: The [.github/workflows/deploy-to-prod.yaml](.github/workflows/deploy-to-prod.yaml) workflow deploys the agent to the production Agent Runtime (`finops-admin-prd`), extracts the production ID, and deploys the BFF container to Production Cloud Run.

For details on network variables, service accounts, and Terraform variable propagation, refer to the [Deployment README](deployment/README.md).

## IAM Permissions & Validation

For the agent and the executive dashboard to discover GCP resources and projects, the querying developer's account (and the deployed application service account) must have the appropriate Cloud Asset Inventory permissions.

Please refer to the [IAM Permissions & Validation](deployment/README.md#iam-permissions--validation) section in the Deployment README for:
- The validation command to verify your user's permissions.
- `gcloud` commands to grant missing roles at the Organization, Folder, or Project level.
- Helper bash scripts to bulk-bind permissions to all projects or standalone (orphaned) projects linked to your billing account.

## Technical Architecture

- **Orchestration**: Built with **Google ADK** for robust agent behavior.
- **APIs**: Google Developer Knowledge API and Cloud Asset Inventory.
- **Data Layer**: Direct semantic schema access to BigQuery via native ADK `BigQueryToolset` and cached SQL query execution.
- **Infrastructure**: GCS-backed remote state for consistent multi-environment management managed via Terraform.
- **Frontend**: React (TypeScript) built with **Stitch** for high information density.
- **Security**: **Identity-Aware Proxy (IAP)** natively integrated with Cloud Run for enterprise-grade authentication, restricting access to authorized users within the organization.
- **Deployment**: **Unified Container** architecture hosted on **Google Cloud Run**.
