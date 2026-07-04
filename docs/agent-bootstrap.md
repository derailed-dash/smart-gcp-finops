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

## 8. Dataplex Dependency and Remote API 404 Routing Resolution (2026-07-02)

- **Issue 1 (Import Error):** The remote Agent Runtime container crashed at startup with:
  ```text
  ImportError: cannot import name 'dataplex_v1' from 'google.cloud'
  ```
  *Why:* ADK's `BigQueryToolset` depends internally on the `google-cloud-dataplex` package. When we pruned dependencies to optimize container sizes, we accidentally omitted Dataplex.
  *Resolution:* Added `google-cloud-dataplex` to the dependencies in [app/pyproject.toml](file:///home/dazbo/localdev/smart-gcp-finops/app/pyproject.toml) and re-compiled [requirements.txt](file:///home/dazbo/localdev/smart-gcp-finops/app/finops_agent/requirements.txt).

- **Issue 2 (404 Mapped Routing):** Remote calls to the container returned HTTP `404 Not Found` (detail: `"Not Found"`) from the Agent Platform Control Plane.
  *Why:* To suppress warning logs, we had pruned the `"async"` and `"async_stream"` keys from `register_operations()` in `agent_runtime_app.py`. However, the Agent Platform control plane uses these keys to construct its routing tables; removing them broke the routing paths.
  *Resolution:* Restored the original keys in `register_operations()`, confirming that the client-side warning is harmless, whereas removing the keys breaks execution.

## 9. Bypassing SDK Streaming Hang with Unary Mode (2026-07-02)

- **Issue:** The agent execution hung indefinitely immediately after logging:
  ```text
  models.py:8686 - AFC is enabled with max remote calls: 10.
  ```
  *Why:* The `google-genai` SDK version 2.x contains a known client-side bug where combining **Automatic Function Calling (AFC)** with **streaming** (`generate_content_stream`) on the Gemini Enterprise Agent Platform results in a deadlocked thread that hangs and fails to return the final text response.
  *Resolution:* Bypassed the streaming bug by instructing the ADK runner inside the Agent Runtime container to execute in unary (non-streaming) mode by injecting `run_config={"streaming_mode": None}`:
  ```python
  async for event_dict in agent_engine.async_stream_query(
      message=augmented_message,
      user_id=user_email,
      session_id=AppState.remote_session_id,
      run_config={"streaming_mode": None},
  ):
      event = Event.model_validate(event_dict)
      await event_queue.put(event)
  ```

## 10. BFF Response Swallowing and Stream Recovery (2026-07-02)

- **Issue:** The UI received empty chat bubbles, and the BFF logged very low latencies (e.g., 2.2 seconds) and returned empty responses.
  *Why:* The BFF event generator loop had an `if not is_final:` filter. This was designed to skip the final accumulated response in streaming mode to prevent showing duplicate text. However, in unary mode, the engine only returns a single event where `is_final_response()` is `True` and `partial` is `False`. The filter skipped this final event, resulting in a blank response.
  *Resolution:* Modified [bff/fast_api_app.py](file:///home/dazbo/localdev/smart-gcp-finops/bff/fast_api_app.py) to check `event.partial` to keep track of whether any partial text has been yielded:
  ```python
  is_partial = getattr(event, "partial", False)
  if hasattr(event, "content") and event.content:
      parts = event.content.parts if hasattr(event.content, "parts") else []
      text_chunk = "".join(
          part.text for part in parts if hasattr(part, "text") and part.text
      )
      if text_chunk:
          if is_partial:
              has_yielded_partial_text = True
              yield "data: " + json.dumps({"text": text_chunk}) + "\n\n"
          elif not has_yielded_partial_text:
              yield "data: " + json.dumps({"text": text_chunk}) + "\n\n"
  ```
  This handles both normal streaming (yield chunks, skip final duplicate) and unary mode (yield the single final response).

## 11. Debug Logging and Deployment Configurations (2026-07-02)

- **Resolution:** Added detailed `logger.debug` tracing to log:
  1. Session creation arguments and results.
  2. Incoming remote JSON payloads from the `agent_engine.async_stream_query()` generator.
  3. Structured stack trace dumps on execution failures.
- **Usage:** Developers can deploy with debug logging enabled by specifying `LOG_LEVEL` in the deployment targets:
  ```bash
  make deploy-cloud-run LOG_LEVEL=DEBUG
  ```

## 12. Separate UI/BFF and Agent Runtime Deployment (2026-07-04)

- **Goal:** Separation of concerns in production by deploying the Backend-for-Frontend (BFF) & React UI container to Cloud Run, whilst routing cognitive reasoning loops to the remote Agent Runtime.
- **Resolution:**
  1. **Conditional Lifespan in FastAPI BFF:** Modified [bff/fast_api_app.py](file:///home/dazbo/localdev/smart-gcp-finops/bff/fast_api_app.py) to check for `AGENT_RUNTIME_ID`. If present (production remote mode), it skips loading the local agent package, skips initialising the local runner, and bypasses local A2A route attachment. This saves memory, reduces CPU usage, and isolates the BFF runtime from the agent execution path.
  2. **Dedicated Cloud Run Dockerfile Target:** Created [deployment/cloudbuild-bff.yaml](file:///home/dazbo/localdev/smart-gcp-finops/deployment/cloudbuild-bff.yaml) and updated the `Makefile` `deploy-cloud-run` target to use it. This was necessary because the `gcloud builds submit` command's `--tag` shortcut does not support specifying a custom Dockerfile with `--dockerfile`. The build now correctly builds `bff/Dockerfile` using Cloud Build, whilst keeping the root `Dockerfile` (unified) for local developer container testing.
  3. **CI/CD Workflow Update:** Updated `.github/workflows/staging.yaml` build step to compile the image using `-f bff/Dockerfile` instead of the root `Dockerfile`.
  4. **Verification:** Verified that all unit and E2E integration tests continue to build and pass successfully.
  5. **Telemetry Hardening:** Explicitly configured the `GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY=true`, `OTEL_SEMCONV_STABILITY_OPT_IN=gen_ai_latest_experimental`, and `OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=EVENT_ONLY` environment variables in the Agent Runtime deployment pipelines. This enables full OpenTelemetry tracing and captures input/output content (prompts, responses, and tool definitions) in trace spans, which is mandatory for offline evaluations and online platform monitoring.

