# FinSavant: Dazbo's Google Cloud FinOps Intelligence

An agentic FinOps solution for Google Cloud Platform (GCP) created by [Dazbo](https://dazbo.co.uk) that empowers Cloud Platform Engineers and FinOps Practitioners to manage, understand, and optimise cloud spend across their entire organization.

## Features

- **BigQuery Billing Integration**: Direct access to BigQuery billing exports for cross-project cost analysis.
- **BigQuery MCP (Model Context Protocol)**: Native dataset and table awareness for semantic data querying.
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
├── notebooks/         # Jupyter notebooks for prototyping and evaluation
├── tests/             # Unit and integration tests
├── .gemini/           # Gemini CLI configuration (MCP settings)
├── GEMINI.md          # AI-assisted development guide (ADK best practices)
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
| `make run-backend`   | Run the Backend BFF Server (FastAPI + ADK Agent)                  |
| `make run-frontend`  | Launch the Vite Dev Server for the React UI                       |
| `make lint`          | Run backend code quality checks (`ruff`, `codespell`, `ty`)       |
| `make test-ui`       | Run frontend compiler and lint checks (TypeScript, ESLint)        |
| `make test`          | Run unit and integration tests (`pytest`)                         |
| `make docker-build`  | Build the unified production container locally                    |
| `make docker-run`    | Run the unified container locally with ADC credentials            |
| `make run`           | Shortcut for `make docker-run` to run the container locally        |
| `make tf-plan`       | Initialize Terraform and plan infrastructure deployment           |
| `make tf-apply`      | Initialize Terraform and apply deployment configuration           |
| `make deploy-cloud-run` | Deploy unified container to Cloud Run using Cloud Build          |


## Local Development & Testing Flow

To run the full React frontend and FastAPI backend locally, follow this developer workflow:

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

## CI/CD & Deployment Flow

FinSavant utilizes a decoupled GitHub Actions pipeline to enforce a strict quality gate before releasing code to Production:

1. **Continuous Integration (Staging)**: Pushes or merges to the `main` branch automatically build the unified container image and deploy it to the **Staging** environment (`finops-admin-dev`).
2. **Verification**: Verify the staging environment to ensure all agent tools, BigQuery MCP connections, and React component renders function correctly.
3. **Manual Gate (Production)**: Once verified, deploy the exact same image to the **Production** environment (`finops-admin-prd`) manually:
   - Navigate to the **Actions** tab in the GitHub repository.
   - Select the **Deploy to Production** workflow from the left sidebar.
   - Click the **Run workflow** dropdown and then the **Run workflow** button.

For details on network variables, service accounts, and Terraform variable propagation, refer to the [Deployment README](file:///home/dazbo/localdev/smart-gcp-finops/deployment/README.md).

## Technical Architecture


- **Orchestration**: Built with **Google ADK** for robust agent behavior.
- **APIs**: Remote BigQuery MCP, Google Developer Knowledge API, and Cloud Asset Inventory.
- **Data Layer**: Direct semantic access to BigQuery via the **Model Context Protocol (MCP)**.
- **Infrastructure**: GCS-backed remote state for consistent multi-environment management managed via Terraform.
- **Frontend**: React (TypeScript) built with **Stitch** for high information density.
- **Security**: **Identity-Aware Proxy (IAP)** natively integrated with Cloud Run for enterprise-grade authentication, restricting access to authorized users within the organization.
- **Deployment**: **Unified Container** architecture hosted on **Google Cloud Run**.
