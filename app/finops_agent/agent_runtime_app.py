"""
Description: Agent Runtime application bootstrapper.
Why: Connects the locally defined root agent to the Gemini Enterprise Agent Runtime.
How: Instantiates and initializes the ADK agent runtime and exports the Agent Runtime deployment configuration.
"""
# ruff: noqa: E402  # Setup logging suppressions early to catch import-time warnings from subsequent packages

import logging
import os
import sys
from typing import Any

# Ensure the parent directory is in sys.path so that 'import finops_agent' resolves correctly
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from finops_agent.app_utils.logging_and_telemetry import (
    setup_logging_suppressions,
    setup_telemetry,
)

setup_logging_suppressions()

import google.cloud.logging
import vertexai
from dotenv import load_dotenv
from google.adk.artifacts import GcsArtifactService, InMemoryArtifactService
from vertexai.agent_engines.templates.adk import AdkApp

# Monkeypatching for auto_create_session.
# TODO(derailed-dash): Remove this monkeypatch once the Google ADK team implements native
# support for configuring 'auto_create_session' via environment variables or a standard App config.
# Verified against: google-adk >= 2.3.0, < 3.0.0
# Why: Standard Vertex AI Console Playground queries the reasoning engine directly,
# bypassing the custom AppState configuration in the BFF, which triggers SessionNotFoundError.
# Enforcing auto_create_session = True globally ensures that transient sessions are handled gracefully.
try:
    _original_set_up = AdkApp.set_up

    def _patched_set_up(self) -> None:
        _original_set_up(self)
        if runner := self._tmpl_attrs.get("runner"):
            runner.auto_create_session = True
        if in_memory_runner := self._tmpl_attrs.get("in_memory_runner"):
            in_memory_runner.auto_create_session = True

    AdkApp.set_up = _patched_set_up

    from google.adk.runners import Runner

    _original_runner_init = Runner.__init__

    def _patched_runner_init(self, *args, **kwargs) -> None:
        # Enforce auto_create_session defensively
        kwargs["auto_create_session"] = True
        try:
            _original_runner_init(self, *args, **kwargs)
        except TypeError as e:
            # Fallback if signature changes in future SDK upgrades
            logging.getLogger(__name__).error(
                "ADK Runner.__init__ signature mismatch during monkeypatch execution: %s. "
                "Attempting fallback initialization without custom kwargs.",
                e,
            )
            # Re-try without injecting auto_create_session keyword argument
            kwargs.pop("auto_create_session", None)
            _original_runner_init(self, *args, **kwargs)

    Runner.__init__ = _patched_runner_init
except Exception as e:
    logging.getLogger(__name__).warning(
        "Failed to apply auto_create_session monkeypatches to ADK components: %s. "
        "Vertex AI Console Playground queries may fail if they use stale session IDs.",
        e,
    )


from finops_agent.agent import app as adk_app
from finops_agent.app_utils.typing import Feedback
from finops_agent.config import settings

# Load environment variables from .env file at runtime (mainly for local runner fallback testing)
load_dotenv()


class AgentRuntimeApp(AdkApp):
    def set_up(self) -> None:
        """Initialize the Agent Runtime app with logging and telemetry."""
        vertexai.init()
        setup_telemetry()
        super().set_up()

        # Enable automatic session creation in the underlying ADK runners.
        # This prevents SessionNotFoundError if the console Playground or client
        # sends queries using expired or invalid session IDs (e.g. after container scale-down).
        if runner := self._tmpl_attrs.get("runner"):
            runner.auto_create_session = True
        if in_memory_runner := self._tmpl_attrs.get("in_memory_runner"):
            in_memory_runner.auto_create_session = True

        # Configure logging using standard Python library and cloud-logging backend
        otel_to_cloud = (os.getenv("K_SERVICE") is not None) or (
            os.getenv("OTEL_TO_CLOUD", "false").lower() == "true"
        )
        if otel_to_cloud:
            try:
                logging_client = google.cloud.logging.Client()
                logging_client.setup_logging()
            except Exception:
                logging.basicConfig(level=settings.log_level.upper())
        else:
            logging.basicConfig(level=settings.log_level.upper())

        logging.getLogger().setLevel(settings.log_level.upper())
        setup_logging_suppressions()

        self.logger = logging.getLogger(__name__)

        gemini_location = os.environ.get("GOOGLE_CLOUD_LOCATION")
        if gemini_location:
            os.environ["GOOGLE_CLOUD_LOCATION"] = gemini_location

    def register_feedback(self, feedback: dict[str, Any]) -> None:
        """Collect and log feedback."""
        feedback_obj = Feedback.model_validate(feedback)
        self.logger.info(
            "Feedback received: %s",
            feedback_obj.model_dump(),
            extra={"json_fields": feedback_obj.model_dump()},
        )

    def register_operations(self) -> dict[str, list[str]]:
        """Registers the operations of the Agent."""
        operations = super().register_operations()

        # Force-register standard query methods to bypass the cloud-side inspection bug
        standard_ops = [
            "query",
            "async_query",
            "stream_query",
            "async_stream_query",
            "register_feedback",
        ]
        existing_ops = operations.get("", [])

        # Merge existing operations with the standard required operations
        operations[""] = list(set(existing_ops + standard_ops))
        return operations

    def clone(self) -> "AgentRuntimeApp":
        """Returns a clone of the Agent Runtime application."""
        return self


logs_bucket_name = os.environ.get("LOGS_BUCKET_NAME")
agent_runtime = AgentRuntimeApp(
    app=adk_app,
    artifact_service_builder=lambda: (
        GcsArtifactService(bucket_name=logs_bucket_name)
        if logs_bucket_name
        else InMemoryArtifactService()
    ),
)
