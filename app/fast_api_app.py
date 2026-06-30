"""
Description: Backend BFF FastAPI application.
Why: Serves as the Backend-for-Frontend (BFF) proxy and static React asset host on Cloud Run.
How: Sets up FastAPI endpoints, handles IAP user authentication headers, resolves project access scoping, and proxies chat requests to the remote Agent Runtime or runs a local ADK fallback thread.
"""

import asyncio
import json
import os

import google.auth
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from google.adk.cli.fast_api import get_fast_api_app
from google.cloud import logging as google_cloud_logging

from app.app_utils.context import ALLOWED_PROJECTS_VAR
from app.app_utils.project_discovery import get_user_accessible_projects
from app.app_utils.telemetry import setup_telemetry
from app.app_utils.typing import Feedback

setup_telemetry()
_, project_id = google.auth.default()
logging_client = google_cloud_logging.Client()
logger = logging_client.logger(__name__)
_background_tasks = set()
allow_origins = (
    os.getenv("ALLOW_ORIGINS", "").split(",")
    if os.getenv("ALLOW_ORIGINS")
    else [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:8000",
        "http://127.0.0.1:8000",
    ]
)

# Artifact bucket for ADK (created by Terraform, passed via env var)
logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")

AGENT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# In-memory session configuration - no persistent storage
session_service_uri = None

artifact_service_uri = f"gs://{logs_bucket_name}" if logs_bucket_name else None

# Enable OpenTelemetry Cloud exporting in Cloud Run (prod) or if explicitly requested locally
otel_to_cloud = (os.getenv("K_SERVICE") is not None) or (
    os.getenv("OTEL_TO_CLOUD", "false").lower() == "true"
)

app: FastAPI = get_fast_api_app(
    agents_dir=AGENT_DIR,
    web=False,
    artifact_service_uri=artifact_service_uri,
    allow_origins=allow_origins,
    session_service_uri=session_service_uri,
    otel_to_cloud=otel_to_cloud,
)
app.title = "smart-gcp-finops"
app.description = "API for interacting with the Agent smart-gcp-finops"

# Thread-safe lazy-initialisation helper for global ADK session and runner by user
_GLOBAL_SESSION_SERVICE = None
_GLOBAL_SESSIONS = {}
_GLOBAL_RUNNER = None
_INIT_LOCK = asyncio.Lock()
_REMOTE_SESSION_ID = None
_REMOTE_SESSION_LOCK = asyncio.Lock()


def _get_user_email(request: Request) -> str:
    """Extracts the authenticated user email from IAP headers, falling back to local settings."""
    user_email = request.headers.get("X-Goog-Authenticated-User-Email", "")
    if user_email.startswith("accounts.google.com:"):
        return user_email.split("accounts.google.com:")[-1]
    elif user_email.startswith("mailto:"):
        return user_email.split("mailto:")[-1]
    elif user_email:
        return user_email
    from app.config import settings
    return settings.local_developer_email


async def get_global_runner_and_session(user_email: str = "default_user"):
    """Initialises and returns a persistent global Runner and Session to preserve conversation memory."""
    global _GLOBAL_SESSION_SERVICE, _GLOBAL_SESSIONS, _GLOBAL_RUNNER
    async with _INIT_LOCK:
        if _GLOBAL_RUNNER is None:
            from google.adk.runners import Runner
            from google.adk.sessions import InMemorySessionService

            from app.agent import root_agent

            _GLOBAL_SESSION_SERVICE = InMemorySessionService()
            _GLOBAL_RUNNER = Runner(
                agent=root_agent,
                session_service=_GLOBAL_SESSION_SERVICE,
                app_name="smart-gcp-finops",
            )

        if user_email not in _GLOBAL_SESSIONS:
            session = _GLOBAL_SESSION_SERVICE.create_session_sync(
                user_id=user_email, session_id=user_email, app_name="smart-gcp-finops"
            )
            _GLOBAL_SESSIONS[user_email] = session

        return _GLOBAL_RUNNER, _GLOBAL_SESSIONS[user_email]


@app.get("/api/status")
def get_status() -> dict:
    """Returns the operational status of the agent (local fallback vs remote runtime)."""
    agent_runtime_id = os.environ.get("AGENT_RUNTIME_ID")
    return {
        "mode": "remote" if agent_runtime_id else "local",
        "agent_runtime_id": agent_runtime_id,
    }


@app.get("/api/dashboard")
def get_dashboard(
    request: Request,
    clientDay: int | None = None,
    clientMonthDays: int | None = None,
) -> dict:
    """Returns actual real-time executive dashboard metrics from BQ and CAI."""
    from app.app_utils.dashboard_data import get_actual_dashboard_metrics

    try:
        user_email = _get_user_email(request)
        allowed_projects = get_user_accessible_projects(user_email)
        return get_actual_dashboard_metrics(
            allowed_projects=allowed_projects,
            client_day=clientDay,
            client_month_days=clientMonthDays,
        )
    except Exception as e:
        logger.log_text(f"Error compiling dashboard metrics: {e}", severity="ERROR")
        return {
            "mtdSpend": 0.0,
            "mtdChange": 0.0,
            "forecast": 0.0,
            "forecastLabel": "Projected end-of-month",
            "anomaliesCount": 0,
            "zombieWaste": 0.0,
            "recentSpikes": [],
            "zombies": [],
        }


# Custom SSE streaming chat endpoint with heartbeat
@app.post("/api/chat/stream")
async def chat_stream(request: Request):
    """Streams the ADK agent chat responses using Server-Sent Events (SSE).

    Includes a 15-second heartbeat to prevent Cloud Run timeouts.
    """
    body = await request.json()
    message = body.get("message", "")

    user_email = _get_user_email(request)
    allowed_projects = get_user_accessible_projects(user_email)
    ALLOWED_PROJECTS_VAR.set(allowed_projects)

    agent_runtime_id = os.environ.get("AGENT_RUNTIME_ID")
    if not agent_runtime_id:
        runner, session = await get_global_runner_and_session(user_email)

    async def event_generator():
        # Set the context variable in the generator context
        ALLOWED_PROJECTS_VAR.set(allowed_projects)
        # Yield initial status/reasoning chunk
        initial_reasoning = (
            "Routing query to Gemini Enterprise Agent Runtime...\n"
            if agent_runtime_id
            else "Step 1: Initialising dynamic billing table discovery...\nStep 2: Connected successfully. Spawning agent workflow...\n"
        )
        yield ("data: " + json.dumps({"reasoning": initial_reasoning}) + "\n\n")
        await asyncio.sleep(0.5)

        from google.adk.agents.run_config import RunConfig, StreamingMode
        from google.genai import types

        # Inject dynamic user security instruction into the prompt
        proj_list_str = ", ".join(f"'{p}'" for p in allowed_projects) if allowed_projects else "'__NONE__'"
        security_guard_prompt = (
            f"\n\n[SECURITY CONSTRAINT: You are acting on behalf of the user '{user_email}'. "
            f"This user only has access to the following projects: [{proj_list_str}]. "
            f"You MUST NOT query, summarize, or expose any billing details or resource properties "
            f"associated with any projects NOT in this list. When writing SQL queries, you MUST "
            f"restrict your filters to this project list (e.g. project.id IN ({proj_list_str})).]"
        )
        augmented_message = message + security_guard_prompt
        message_content = types.Content(role="user", parts=[types.Part(text=augmented_message)])

        event_queue = asyncio.Queue()
        loop = asyncio.get_running_loop()

        def run_agent_in_thread():
            try:
                # Propagate context-local allowed projects list to the worker thread
                ALLOWED_PROJECTS_VAR.set(allowed_projects)
                for event in runner.run(
                    new_message=message_content,
                    user_id=user_email,
                    session_id=session.id,
                    run_config=RunConfig(streaming_mode=StreamingMode.SSE),
                ):
                    loop.call_soon_threadsafe(event_queue.put_nowait, event)
            except Exception as e:
                loop.call_soon_threadsafe(event_queue.put_nowait, e)
            finally:
                loop.call_soon_threadsafe(event_queue.put_nowait, None)

        async def run_remote_agent():
            global _REMOTE_SESSION_ID
            try:
                import vertexai
                from google.adk.errors.session_not_found_error import (
                    SessionNotFoundError,
                )
                from google.adk.events.event import Event

                location = os.environ.get("GOOGLE_CLOUD_REGION", "europe-west1")
                client = vertexai.Client(location=location)
                agent_engine = client.agent_engines.get(name=agent_runtime_id)

                async with _REMOTE_SESSION_LOCK:
                    if _REMOTE_SESSION_ID is None:
                        session_obj = await agent_engine.async_create_session(
                            user_id=user_email
                        )
                        _REMOTE_SESSION_ID = (
                            session_obj.get("id")
                            if isinstance(session_obj, dict)
                            else getattr(session_obj, "id", None)
                        )
                        if not _REMOTE_SESSION_ID:
                            _REMOTE_SESSION_ID = str(session_obj)

                try:
                    async for event_dict in agent_engine.async_stream_query(
                        message=augmented_message,
                        user_id=user_email,
                        session_id=_REMOTE_SESSION_ID,
                    ):
                        event = Event.model_validate(event_dict)
                        await event_queue.put(event)
                except SessionNotFoundError:
                    logger.log_text(
                        "Remote session not found/expired. Resetting session and retrying.",
                        severity="WARNING",
                    )
                    async with _REMOTE_SESSION_LOCK:
                        _REMOTE_SESSION_ID = None
                    async for event_dict in agent_engine.async_stream_query(
                        message=message, user_id="default_user"
                    ):
                        event = Event.model_validate(event_dict)
                        await event_queue.put(event)
            except Exception as e:
                await event_queue.put(e)
            finally:
                await event_queue.put(None)

        if agent_runtime_id:
            task = asyncio.create_task(run_remote_agent())
            _background_tasks.add(task)
            task.add_done_callback(_background_tasks.discard)
        else:
            import threading

            threading.Thread(target=run_agent_in_thread, daemon=True).start()

        seen_function_calls = set()
        seen_function_responses = set()
        seconds_passed = 0
        while True:
            # Proactively check if client has disconnected (closes tab or refreshes)
            if await request.is_disconnected():
                logger.log_text(
                    "Client disconnected from chat stream.", severity="INFO"
                )
                break

            try:
                # Non-blocking wait for next event from the queue (timeouts do not cancel the generator)
                event = await asyncio.wait_for(event_queue.get(), timeout=1.0)
            except TimeoutError:
                seconds_passed += 1
                if seconds_passed >= 15:
                    yield ": heartbeat\n\n"
                    seconds_passed = 0
                continue

            if event is None:
                break

            if isinstance(event, Exception):
                logger.log_text(
                    f"Error in background runner: {event}", severity="ERROR"
                )
                import traceback

                yield (
                    "data: "
                    + json.dumps(
                        {
                            "reasoning": f"❌ Error: {event!s}\n{traceback.format_exc()}\n"
                        }
                    )
                    + "\n\n"
                )
                break

            seconds_passed = 0

            # Stream real-time text chunks
            is_final = False
            if hasattr(event, "is_final_response"):
                try:
                    is_final = event.is_final_response()
                except Exception:
                    pass

            if not is_final and hasattr(event, "content") and event.content:
                parts = event.content.parts if hasattr(event.content, "parts") else []
                text_chunk = "".join(
                    part.text for part in parts if hasattr(part, "text") and part.text
                )
                if text_chunk:
                    yield "data: " + json.dumps({"text": text_chunk}) + "\n\n"

            # Stream intermediate reasoning/tool status updates
            if hasattr(event, "status") and event.status:
                yield "data: " + json.dumps({"reasoning": f"{event.status}\n"}) + "\n\n"

            # Stream granular function calls and responses in flight
            if hasattr(event, "get_function_calls"):
                try:
                    for fc in event.get_function_calls():
                        if fc and fc.name:
                            # Build a unique key for deduplication
                            args_str = ""
                            if hasattr(fc, "args") and fc.args:
                                try:
                                    args_str = json.dumps(fc.args, sort_keys=True)
                                except Exception:
                                    args_str = str(fc.args)
                            fc_id = getattr(fc, "id", "")
                            call_key = f"{fc.name}:{args_str}:{fc_id}"
                            if call_key not in seen_function_calls:
                                seen_function_calls.add(call_key)
                                yield (
                                    "data: "
                                    + json.dumps(
                                        {
                                            "reasoning": f"⚙️ Tool Call: Invoking {fc.name}...\n"
                                        }
                                    )
                                    + "\n\n"
                                )
                except Exception:
                    pass

            if hasattr(event, "get_function_responses"):
                try:
                    for fr in event.get_function_responses():
                        if fr and fr.name:
                            # Build a unique key for deduplication
                            resp_str = ""
                            if hasattr(fr, "response") and fr.response:
                                try:
                                    resp_str = json.dumps(fr.response, sort_keys=True)
                                except Exception:
                                    resp_str = str(fr.response)
                            fr_id = getattr(fr, "id", "")
                            resp_key = f"{fr.name}:{resp_str}:{fr_id}"
                            if resp_key not in seen_function_responses:
                                seen_function_responses.add(resp_key)
                                yield (
                                    "data: "
                                    + json.dumps(
                                        {
                                            "reasoning": f"✅ Tool Complete: {fr.name} response received\n"
                                        }
                                    )
                                    + "\n\n"
                                )
                except Exception:
                    pass

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.post("/feedback")
def collect_feedback(feedback: Feedback) -> dict[str, str]:
    """Collect and log feedback.

    Args:
        feedback: The feedback data to log

    Returns:
        Success message
    """
    logger.log_struct(feedback.model_dump(), severity="INFO")
    return {"status": "success"}


# Serve the static pre-compiled React frontend SPA assets in production
FRONTEND_DIST = os.path.abspath(
    os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
)

if os.path.exists(FRONTEND_DIST):
    # Mount the /assets static assets subfolder
    app.mount(
        "/assets",
        StaticFiles(directory=os.path.join(FRONTEND_DIST, "assets")),
        name="assets",
    )

    # Catch-all route to serve the SPA index.html for any frontend navigation paths
    @app.get("/{fallback_path:path}")
    async def spa_fallback(fallback_path: str):
        # Allow API, events, and feedback endpoints to be processed normally by other routers
        if (
            fallback_path.startswith("api")
            or fallback_path.startswith("events")
            or fallback_path.startswith("feedback")
            or fallback_path.startswith("docs")
            or fallback_path.startswith("openapi.json")
        ):
            raise HTTPException(status_code=404, detail="Endpoint not found")

        # Serve the file directly if it exists in the frontend dist directory (e.g. favicon.ico, vite.svg)
        file_path = os.path.join(FRONTEND_DIST, fallback_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)

        index_file = os.path.join(FRONTEND_DIST, "index.html")
        if os.path.exists(index_file):
            return FileResponse(index_file)
        raise HTTPException(status_code=404, detail="Index file not found")


# Main execution
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
