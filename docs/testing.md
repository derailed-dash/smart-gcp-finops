# FinSavant - Testing Guide

This document defines how we verify the correctness and security of the **FinSavant** application (developed by [Dazbo](https://dazbo.co.uk)).

## Quality Gates

- **Unit Testing**: 100% of core business and agent logic must have unit tests.
- **Code Coverage**: Minimum >80% coverage for all new Python and TypeScript code.
- **TDD (Test-Driven Development)**: Prefer writing failing tests before implementing features.
- **Linting & Safety**: No errors from `ruff`, `codespell`, or static analysis.

## Tooling

### Python (Backend & Agent)

- **Framework**: `pytest`
- **Coverage**: `pytest-cov`
- **Mocks**: `pytest-mock` (for mocking GCP APIs and MCP calls).
- **Type Checking**: `ty` (Astral's type checker) and standard Python type hints.

### React (Frontend)

- **Language Compiler**: `TypeScript` (specifically `tsc` for type-checking).
- **Framework & Bundler**: `Vite 6.4.2` (Strictly a development-only tool used for local hot-reloading compilation and compiling optimized production static assets; never packaged or executed inside the production Cloud Run image).
- **Sub-Dependency Security**: `esbuild ^0.25.0` (Pinned via npm overrides to patch development-server vulnerabilities).
- **Icons**: `Lucide React` (for vector iconography).
- **Linter**: `ESLint` (pre-configured to enforce standard hooks and typescript usage).
- **E2E Testing**: `Playwright` (planned for critical user flows like IAP login).

## Running Tests

### Backend (Python & Agent)

#### Automated Suite

Run all backend tests and generate a coverage report:
```bash
make test
# Equivalent to: pytest --cov=app --cov-report=term-missing
```

#### Selective Testing

Run only unit tests:
```bash
pytest tests/unit
```

Run only semantic caching unit tests:
```bash
pytest tests/unit/test_semantic_cache.py
```
This suite validates the GenAI Semantic Caching engine by mocking the Google GenAI `Client`'s response generation to verify hit, miss, and save cache loops in a mock-driven, deterministic environment.

Run only integration tests (requires active GCP credentials):
```bash
pytest tests/integration
```

### Frontend (React & TypeScript)

#### TypeScript Compilation Check

To verify that the React application is type-safe and has zero syntax or compiler issues, compile the static bundle:
```bash
cd frontend
npm run build
```
This executes `tsc` (TypeScript compiler) and `vite build` under the hood. All files must compile with **zero errors** or warning blocks.

#### Development Lint Gating

To run eslint code analysis across all TSX files:
```bash
cd frontend
npm run lint
```

## Manual Verification

### BigQuery MCP Verification (Gemini CLI)

The fastest way to verify your local environment is correctly configured for the BigQuery MCP is to query the agent directly from the Gemini CLI.

**Check Dataset Visibility**:
> "what bq datasets do we have in GOOGLE_CLOUD_BILLING_PROJECT?"

**Expected Result**: The agent should use `bigquery-mcp-server_list_dataset_ids` and return `all_billing_data`.

**Check Table Visibility**:
> "list the tables in the all_billing_data dataset in GOOGLE_CLOUD_BILLING_PROJECT"

**Expected Result**: The agent should return the `gcp_billing_export_v1_...` tables.

**Quota Project Header (`x-goog-user-project`)**:
When testing across projects, ensure your `.gemini/settings.json` includes the `x-goog-user-project` header. Without this, BigQuery may attempt to bill the query to the project containing the data, which often results in `403: Access Denied` if your identity only has data-level permissions.

### BigQuery CLI Connectivity

If the MCP check fails, verify raw connectivity via the `bq` CLI.
```bash
# Verify billing project query access
# Note: billing_account_id is converted to underscores in the BigQuery table name
BILLING_TABLE_SUFFIX=$(echo $GOOGLE_CLOUD_BILLING_ACCOUNT | tr '-' '_')

# Option 1: Pretty Table (Standard bordered output)
bq query --use_legacy_sql=false --location=$GOOGLE_CLOUD_BILLING_LOCATION --project_id=$GOOGLE_CLOUD_BILLING_PROJECT \
  --format=pretty \
  "SELECT project.id as project, service.description as service, sku.description as sku, FORMAT('%.2f', cost) as cost, currency FROM \`${GOOGLE_CLOUD_BILLING_PROJECT}.${BILLING_EXPORT_DATASET}.gcp_billing_export_v1_${BILLING_TABLE_SUFFIX}\` WHERE usage_start_time >= TIMESTAMP_SUB(CURRENT_TIMESTAMP(), INTERVAL 30 DAY) ORDER BY cost DESC LIMIT 5"
```

### API Endpoint Check

Verify the FastAPI backend is responding correctly:
```bash
curl -X GET http://localhost:8000/api/health
```

### Agent SSE Stream Check

Verify the agent's real-time thinking stream:
```bash
curl -N -X POST http://localhost:8000/run_sse \
  -H "Content-Type: application/json" \
  -d '{"new_message": {"parts": [{"text": "Summarize my cloud spend."}]}}'
```

### Billing Project Discovery Verification

Verify the logic that maps the infrastructure footprint via the Billing API:
```bash
# Ensure GOOGLE_CLOUD_BILLING_ACCOUNT is set in your environment
uv run python -c "from app.app_utils.project_discovery import list_billing_projects; import os; print(list_billing_projects(f'billingAccounts/{os.getenv(\"GOOGLE_CLOUD_BILLING_ACCOUNT\")}'))"
```
**Expected Result**: A Python list of Project IDs linked to the billing account. If you receive an empty list or a `403`, verify the **Cloud Billing API** is enabled and the identity has `roles/billing.viewer`.

### Infrastructure Asset Inspection Verification

Verify that the identity (or agent service account) has the necessary "Eyes" to look inside a discovered project using the Cloud Asset Inventory (CAI) API.

**Verification Script**:
Run this command to test asset visibility for a specific `PROJECT_ID`.

```bash
uv run python - <<EOF
from googleapiclient import discovery
from google.auth import default
try:
    creds, _ = default()
    service = discovery.build('cloudasset', 'v1', credentials=creds)
    project_id = 'YOUR_PROJECT_ID' # e.g., finops-admin-dev
    parent = f'projects/{project_id}'
    res = service.assets().list(parent=parent).execute()
    assets = res.get("assets", [])
    print(f'SUCCESS: Found {len(assets)} assets in {project_id}')
    if assets:
        print(f'First asset: {assets[0].get("name")}')
except Exception as e:
    print(f'FAILURE: {e}')
EOF
```

**Why this matters**: 
Discovery (the "Map") only finds the project IDs. Inspection (the "Eyes") requires **`roles/cloudasset.viewer`** and the **Cloud Asset API** to be enabled in the target project. Without both, the agent will be able to see that a project exists but will be unable to analyze its resources for FinOps optimizations.

### Tool Routing & Cloud Assist Validation (GCA Routing Tree)

We use a strict tool-routing decision tree (Approach A) to prevent multi-tool chaining and reduce response latency. The agent categorizes queries into one of four routes and disables all other toolsets.

To manually verify that the agent is routing queries correctly, launch the playground (`make playground`) or use the React interface, and test the following scenarios:

#### Route 1: Spend & Historical Trends (BigQuery Cache Route)
*   **Test Prompt**: `"What was our monthly spend for Compute Engine over the last 90 days?"`
*   **Expected Behavior**: The agent should call ONLY the cached BigQuery tool (`execute_cached_bigquery_sql`).
*   **Verification**: Ensure the agent does NOT call CAI or Search Documents. The response should display cost numbers in the conversational text and update the area chart or pivot table on the Canvas.

#### Route 2: Active Infrastructure Optimization & Troubleshooting (Cloud Assist Route)
*   **Test Prompt**: `"Use Cloud Assist to check for cost or scaling recommendations for our deployed Cloud Run service `smart-gcp-finops` in project `finops-admin-dev`."` or `"Troubleshoot the latest deployment of `smart-gcp-finops` in `finops-admin-dev` using Cloud Assist."`
*   **Expected Behavior**: The agent should call ONLY the Gemini Cloud Assist MCP tool (`gemini-cloud-assist_ask_cloud_assist`).
*   **Verification**: Ensure the agent does NOT run general BigQuery billing queries or call generic document searches. The response should contain specific, live recommendations or diagnostics for the named Cloud Run service (e.g., suggesting rightsizing or detailing active revision logs).

#### Route 3: Structured Asset Audits & Config History (CAI Route)
*   **Test Prompt**: `"Do we have any unattached persistent disks?"` or `"List all VMs currently running in our project."`
*   **Expected Behavior**: The agent should call ONLY local CAI / zombie tools (`list_zombie_resources` or `get_cai_metadata_for_resources`).
*   **Verification**: Ensure the agent does NOT query BigQuery billing tables or call Cloud Assist. The Canvas should display the discovered assets (disks or VMs) in a structured Recommendations table.

#### Route 4: Conceptual Reference Q&A (Developer Knowledge Route)
*   **Test Prompt**: `"What is the difference between Nearline and Coldline storage classes, and when should I use each?"`
*   **Expected Behavior**: The agent should call ONLY the Google Developer Knowledge MCP tools (`answer_query` or `search_documents`).
*   **Verification**: Ensure the agent does NOT query BigQuery billing, list CAI assets, or call Cloud Assist. The response should explain the concept conceptually with clickable documentation links/citations.

### React Split-Screen & SSE Chat (Emerald Cyber UI)

To manually verify the full end-to-end integration and visual correctness of the **Emerald Cyber** interface:

1.  **Start the FastAPI Backend**:
    From the root folder, run the local uvicorn API server:
    ```bash
    uv run python -m app.fast_api_app
    ```
    This launches the backend on `http://localhost:8000`.

2.  **Start the Vite Frontend**:
    Open a separate terminal window, navigate to the `/frontend` directory, and run the development server:
    ```bash
    cd frontend
    npm run dev
    ```
    This launches the UI on `http://localhost:5173`.

3.  **Verify Layout & Rendering**:
    *   Open `http://localhost:5173` in your browser.
    *   Verify that the viewport is split into the **Left Chat Panel** (35% width) and the **Right Workspace Canvas** (65% width) with the deep carbon theme (`#080B0D` background, glowing green highlights).
    *   Confirm that the four KPI cards render correct metrics and have glowing vector top borders.
    *   Confirm that the daily cost stacked area chart is correctly drawn via inline vector SVGs with glowing neon curves and vertical glow gradients.
    *   Verify that the **"Analyze Cost Spikes"** chat starter chip is initially disabled and displays **"Resolving Spikes..."** while the dashboard telemetry is loading. Once the dashboard completes loading, confirm it dynamically unlocks as **"Analyze Cost Spikes"** and targets the correct resolved peak date (e.g. `"2nd June"` or `"June 2"`).

4.  **Verify SSE Chat Streaming**:
    *   Type a cost question in the chat input box (e.g., *"Show my top 3 cost drivers"*) and hit enter.
    *   Verify that the agent's intermediate "thoughts" or "reasoning steps" stream incrementally with a terminal icon block.
    *   Confirm that the text answer streams seamlessly, and the right Canvas instantly updates to the **Cost Explorer** view, displaying a dense, sortable pivot table.
    *   Verify that clicking column headers on the table dynamically sorts the data.

5.  **Verify Heartbeat & Idle Handling**:
    *   Ask a complex question that requires deep MCP execution.
    *   Monitor the browser dev tools (Network tab -> `/events` or `/api/chat/stream`). Confirm that the connection remains active and that `keep-alive` heartbeat comment packets (`: heartbeat`) are transmitted every 15 seconds to prevent Cloud Run connection termination.

### Identity-Aware Proxy (IAP) Verification

Once your service is successfully deployed to Cloud Run with native IAP enabled:

1.  **Test from Private/Incognito Browser Session**:
    * Open an incognito browser window and navigate to your deployed Cloud Run service URL.
    * **Expected Result**: The proxy must immediately redirect you to the Google Accounts login page.

2.  **Domain/Organization Gate Validation**:
    > [!IMPORTANT]
    > **Domain Organization Constraint**: Because the OAuth Consent Screen for built-in IAP is configured as **Internal**, Google restricts logins exclusively to accounts belonging to the target organization domain (Workspace/Cloud Identity). When verifying access, you **must use an allowed user account from that exact same domain**. Personal `@gmail.com` accounts or credentials from external domains will be blocked immediately at the Google OAuth consent gate, even if added to `var.iap_access_emails`.

    * **Verify Allowed Account**: Log in using an approved Workspace account that belongs to the same target organization domain (and is added in `var.iap_access_emails`).
      * **Expected Result**: Access is successfully granted, and the **Emerald Cyber** React dashboard renders.
    * **Verify Unauthorized Account**: Attempt to log in using a Workspace account from the target domain that is *not* listed in your allowed emails.
      * **Expected Result**: Access is blocked at the edge with an `HTTP 403 Forbidden` error page served by IAP.

### Unified Container Local Verification


To verify that the unified frontend and backend container builds correctly and serves the React SPA (rather than the ADK Web UI playground) on port 8080:

1.  **Build the Container**:
    Execute the local Docker build target to compile both stages:
    ```bash
    make docker-build
    ```

2.  **Run the Container**:
    Launch the compiled container using the shortcut target:
    ```bash
    make run
    ```
    This securely passes your local Google Application Default Credentials (ADC) and FinOps variables, spinning up uvicorn inside the container on port `8080`.

3.  **Access and Verify**:
    *   Open your browser and navigate to `http://localhost:8080`.
    *   **Success Criteria**: The browser must display your custom React dashboard (the **Emerald Cyber** interface) and NOT the default ADK Web UI developer interface.
    *   Verify that API requests and chat functionality are fully operational.

### Telemetry & OpenTelemetry Tracing Verification

Standard ADK telemetry and OpenTelemetry tracing are integrated into the application startup sequence. This section explains how tracing works under the hood and how to verify and debug it using a local instance or in the cloud.

#### How Tracing Works Under the Hood

The application telemetry is configured in [telemetry.py](file:///home/darren_lester/localdev/my-IP/smart-gcp-finops/app/app_utils/telemetry.py) and initialised during backend startup (in [fast_api_app.py](file:///home/darren_lester/localdev/my-IP/smart-gcp-finops/app/fast_api_app.py) and [agent_runtime_app.py](file:///home/darren_lester/localdev/my-IP/smart-gcp-finops/app/agent_runtime_app.py)).

1. **Standard ADK Tracing & Logging**: If `OTEL_TO_CLOUD` is set to `"true"` (or when running on Cloud Run), the app uses standard `google.adk.telemetry` APIs to configure Google Cloud Trace and Cloud Logging exporters. This is safely initialised via `maybe_set_otel_providers()`, which ensures existing global OpenTelemetry providers are not overridden.
2. **GenAI SDK Instrumentation**: The `GoogleGenAiSdkInstrumentor` from `opentelemetry.instrumentation.google_genai` is loaded to instrument all Gemini model calls. This captures detailed metrics and span events for model queries.
3. **Payload Capture & Logging Hook**:
   - If `LOGS_BUCKET_NAME` is configured and `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT` is not `"false"`, the app configures an upload completion hook to save full prompt/response contents as JSONL files directly to the GCS bucket at `gs://{LOGS_BUCKET_NAME}/completions`.
   - In **Dev/Staging**, payload capture is set to `"true"` to record full text prompts and responses in spans and logs.
   - In **Production**, payload capture is set to `"NO_CONTENT"` to restrict span attributes to metadata only, protecting sensitive customer or billing information.

#### Verifying Tracing in Local Development

For ease of use, all telemetry environment variables are already defined in the local [.env](file:///home/darren_lester/localdev/my-IP/smart-gcp-finops/.env) file:
*   `OTEL_TO_CLOUD="true"`: Enables OpenTelemetry trace export to Google Cloud Trace.
*   `OTEL_SERVICE_NAME="smart-gcp-finops-local"`: The logical service identifier.
*   `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT="true"`: Captures full prompt-response text.

To run and verify local tracing:

1. **Authenticate Application Default Credentials (ADC)**:
   Ensure your shell is authenticated so the local OpenTelemetry exporters can push traces to Google Cloud:
   ```bash
   gcloud auth application-default login
   ```
2. **Load the Environment**:
   If using `direnv`, the environment is loaded automatically. Otherwise, source the setup script:
   ```bash
   source scripts/setup-env.sh
   ```
   This script loads the `.env` variables and configures your active gcloud project/quota project.
3. **Start the Backend**:
   ```bash
   make run-backend
   ```
4. **Generate Traces**:
   Query the agent via the frontend chat interface, the CLI, or by sending a request to the SSE endpoint. For example:
   ```bash
   curl -N -X POST http://localhost:8000/run_sse \
     -H "Content-Type: application/json" \
     -d '{"new_message": {"parts": [{"text": "What was our monthly spend for Compute Engine?"}]}}'
   ```
5. **View Traces in Google Cloud Console**:
   * Open the [Google Cloud Trace Explorer](https://console.cloud.google.com/trace/trace-list) for your configured project (`finops-admin-dev`).
   * Filter traces by Service Name: `smart-gcp-finops-local`.
   * You will see the timeline of spans mapping the full execution path, including:
     - `invocation`: The entry point span.
     - `agent_run`: The ADK agent orchestration process.
     - `call_llm`: The model call span, showing prompt tokens and latency.
     - `execute_tool`: Individual tool executions (e.g. executing BigQuery queries or listing assets).
   * Click on individual spans to view their attributes. In local/dev runs, you will see the full prompt and response content under `gen_ai.prompt` and `gen_ai.completion` attributes.

## Mocking Strategies

### MCP Tool Mocking

When testing the agent, mock the response from MCP servers (BigQuery, Developer Knowledge) to ensure tests are deterministic and independent of cloud connectivity.

```python
# Example Mock
def test_agent_with_mocked_bigquery(mocker):
    mocker.patch("app.agent.query_bigquery", return_value=[{"cost": 100.0, "project": "demo"}])
    # ... rest of the test
```

## Continuous Integration (CI)

Tests are automatically executed on every pull request and push to the `main` branch via **GitHub Actions**. Refer to `.github/workflows/pr_checks.yaml` for the pipeline configuration.

For deployment details, see the [Deployment README](../deployment/README.md).
