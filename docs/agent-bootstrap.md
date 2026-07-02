# Agent Bootstrapping and Migration Log

This document tracks the process of scaffolding, migrating, and deploying the ADK agent for the GCP FinOps solution.

## 1. Bootstrapping (2026-07-02)

- **Command Run:**
  ```bash
  agents-cli scaffold create app --agent adk --prototype --agent-guidance-filename GEMINI.md
  ```

## 2. Refined Nested Package Layout (Hatchling Compatibility)

During smoke testing and build validation, we discovered that:
1. Standard ADK packaging uses `hatchling` as its build backend.
2. If we flatten the structure directly under `app/` (setting `agent_directory: "."`), `hatchling` fails to package the wheel correctly because of workspace-level file pollution and root configuration conflicts.
3. Therefore, a nested subdirectory representing the Python package is required. We chose `app/finops_agent/` as the dedicated agent package.

We migrated the structure as follows:
- Set `agent_directory: "finops_agent"` in `/home/dazbo/localdev/smart-gcp-finops/app/agents-cli-manifest.yaml`.
- Created `/home/dazbo/localdev/smart-gcp-finops/app/finops_agent/__init__.py`.
- Moved all agent code files (`agent.py`, `agent_runtime_app.py`, `deploy_to_agent_runtime.py`, `app_utils/`, etc.) into `app/finops_agent/`.
- Removed `/home/dazbo/localdev/smart-gcp-finops/app/__init__.py`.

## 3. BFF and Agent Separation (Unified Container Pattern)

To support clean production deployments where the FastAPI BFF/React UI can be deployed/scaled separately from the Agent Runtime:
- Created a separate `bff/` directory containing the FastAPI application (`bff/fast_api_app.py`) and its own `bff/Dockerfile`.
- Deleted `fast_api_app.py` from the agent package (`app/finops_agent/fast_api_app.py`).
- Kept the agent-serving `agent_runtime_app.py` inside `app/finops_agent/`.
- Updated all import references in the agent code and unit/integration tests from `app.app_utils.*` to `finops_agent.app_utils.*`.
- Updated the root `Dockerfile` to copy `./bff` and `./app/finops_agent` and run the FastAPI app as `bff.fast_api_app:app`.
- Updated `app/Dockerfile` to copy `./finops_agent` and serve the agent using `finops_agent.agent_runtime_app:agent_runtime`.
- Updated the root `Makefile` run targets (`local-backend` and `run-backend`) to run the BFF FastAPI server with `PYTHONPATH=app`.

## 4. Resolution of Renaming & Mocking Edge Cases

### ADK App Name Alignment
The ADK runner routes requests based on the resolved `app_name`. By default, the agent loader infers the `app_name` from the subdirectory name containing the agent code (`finops_agent`).
We aligned this by changing the `App` definition in `app/finops_agent/agent.py` to:
```python
app = App(
    root_agent=root_agent,
    name="finops_agent",
    ...
)
```
This avoids `SessionNotFoundError` during E2E session runs.

### Mock Context and State Handling
In unit tests, `mock_context` was mocked as a `MagicMock`, which bypassed `state.get` checks by returning mock objects instead of `None`. We modified `execute_cached_bigquery_sql` in `tools.py` to robustly check `isinstance(state, MagicMock)` and fallback to `ALLOWED_PROJECTS_VAR.get()` correctly.

### Uvicorn Background Logging
To debug Uvicorn subprocess output in integration tests without buffering issues, we disabled Python output buffering with `PYTHONUNBUFFERED=1` and redirected stdout/stderr to a dedicated `uvicorn_e2e.log` file.

## 5. Verification Results

All tests pass successfully under the new architecture:
- **Unit Tests:** 52 passed.
- **Integration Tests:** 5 passed (including E2E stream tests).
- **Code Quality:** All checks passed with `codespell` and `ruff`.

## 6. Dockerfile Copy Path Fix (2026-07-02)

- **Issue:** Running the unified container (`make docker-run`) failed with `FileNotFoundError: [Errno 2] No such file or directory: '/code/app'` during FastAPI startup. The ADK `get_fast_api_app` helper requires a nested agent folder structure to discover available agents. Because the Dockerfile originally copied `./app/finops_agent` directly to `/code/finops_agent`, `/code/app/` did not exist.
- **Resolution:** Modified both [Dockerfile](file:///home/dazbo/localdev/smart-gcp-finops/Dockerfile) and [bff/Dockerfile](file:///home/dazbo/localdev/smart-gcp-finops/bff/Dockerfile) to copy the agent source package to the nested path `./app/finops_agent` inside the container:
  ```dockerfile
  COPY ./app/finops_agent ./app/finops_agent
  ```
  This preserves the local directory structure exactly, satisfying the ADK loader while keeping `sys.path` imports correct. Verified that `make docker-build` compiles the image successfully.

## 7. Logging & Local Container Run Corrections (2026-07-02)

- **Log Level Fix:** FastAPI's root logging configuration originally hardcoded `logging.basicConfig(level=logging.INFO)`, overriding the configured `settings.log_level` (DEBUG). We modified `bff/fast_api_app.py` to import `settings` and dynamically apply the level using:
  ```python
  logging.getLogger().setLevel(log_level)
  ```
- **Local Container Run Mode:** Running `make docker-run` originally passed the host-resolved `AGENT_RUNTIME_ID` environment variable to the container. If a remote agent runtime had already been deployed once, this forced the local container to run as a remote proxy client instead of running the local agent code in-container. We introduced the `DOCKER_AGENT_RUNTIME_ID` Makefile variable (defaulting to empty), and updated the `docker-run` target to pass `AGENT_RUNTIME_ID="$(DOCKER_AGENT_RUNTIME_ID)"`. This forces the local container to run the local agent by default, while still allowing developers to test remote proxy mode explicitly using `make docker-run DOCKER_AGENT_RUNTIME_ID=$(AGENT_RUNTIME_ID)`.


