"""
Description: Agent Runtime application bootstrapper.
Why: Connects the locally defined root agent to the Gemini Enterprise Agent Runtime.
How: Instantiates and initializes the ADK agent runtime and exports the Agent Runtime deployment configuration.
"""


import logging
import os
from typing import Any

import google.cloud.logging
import vertexai
from dotenv import load_dotenv
from google.adk.artifacts import GcsArtifactService, InMemoryArtifactService
from vertexai.agent_engines.templates.adk import AdkApp

from app.agent import app as adk_app
from app.app_utils.logging_and_telemetry import (
    setup_logging_suppressions,
    setup_telemetry,
)
from app.app_utils.typing import Feedback
from app.config import settings

# Load environment variables from .env file at runtime (mainly for local runner fallback testing)
load_dotenv()


class AgentRuntimeApp(AdkApp):
    def set_up(self) -> None:
        """Initialize the Agent Runtime app with logging and telemetry."""
        vertexai.init()
        setup_telemetry()
        super().set_up()

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
        operations[""] = [*operations.get("", []), "register_feedback"]
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
