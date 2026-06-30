"""
Description: Logging and telemetry configuration for the application.
Why: Ensures consistent log configurations, warning filters, monitoring, and tracing.
How: Suppresses noisy third-party debug outputs and hooks OpenTelemetry to export to Cloud Trace / GCS.
"""

import logging
import os
import warnings


def setup_telemetry() -> str | None:
    """Configure OpenTelemetry and GenAI telemetry with GCS upload."""

    bucket = os.environ.get("LOGS_BUCKET_NAME")
    capture_content = os.environ.get(
        "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false"
    )
    if bucket and capture_content != "false":
        logging.info("Prompt-response logging enabled - mode: %s", capture_content)
        os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT", "jsonl")
        os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK", "upload")
        os.environ.setdefault(
            "OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental"
        )
        commit_sha = os.environ.get("COMMIT_SHA", "dev")
        os.environ.setdefault(
            "OTEL_RESOURCE_ATTRIBUTES",
            f"service.namespace=smart-gcp-finops,service.version={commit_sha}",
        )
        path = os.environ.get("GENAI_TELEMETRY_PATH", "completions")
        os.environ.setdefault(
            "OTEL_INSTRUMENTATION_GENAI_UPLOAD_BASE_PATH",
            f"gs://{bucket}/{path}",
        )
    else:
        logging.info(
            "Prompt-response logging disabled (set LOGS_BUCKET_NAME=gs://your-bucket and OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT=NO_CONTENT to enable)"
        )

    # Configure OpenTelemetry standard ADK telemetry (tracing, logging, metrics)
    otel_to_cloud = (os.getenv("K_SERVICE") is not None) or (
        os.getenv("OTEL_TO_CLOUD", "false").lower() == "true"
    )

    if otel_to_cloud:
        try:
            import google.auth
            from google.adk.telemetry.google_cloud import (
                get_gcp_exporters,
                get_gcp_resource,
            )
            from google.adk.telemetry.setup import maybe_set_otel_providers

            # Ensure OTEL_SERVICE_NAME is set
            if not os.environ.get("OTEL_SERVICE_NAME"):
                os.environ["OTEL_SERVICE_NAME"] = "smart-gcp-finops"

            credentials, project_id = google.auth.default()
            gcp_exporters = get_gcp_exporters(
                enable_cloud_tracing=True,
                enable_cloud_logging=True,
                enable_cloud_metrics=False,
                google_auth=(credentials, project_id),
            )
            otel_resource = get_gcp_resource(project_id)

            maybe_set_otel_providers(
                otel_hooks_to_setup=[gcp_exporters],
                otel_resource=otel_resource,
            )
            logging.info(
                "Standard ADK Telemetry initialized with Google Cloud exporters."
            )
        except Exception as e:
            logging.error("Failed to initialize standard ADK Telemetry: %s", e)

    # Call instrumentation for Google GenAI SDK if installed
    try:
        from opentelemetry.instrumentation.google_genai import (
            GoogleGenAiSdkInstrumentor,
        )

        GoogleGenAiSdkInstrumentor().instrument()
        logging.info("Google GenAI SDK instrumented successfully.")
    except Exception as e:
        logging.warning("Failed to instrument Google GenAI SDK: %s", e)

    return bucket


def setup_logging_suppressions() -> None:
    """Configures Python logging levels and warning filters to suppress noisy third-party outputs."""
    # Suppress experimental feature warnings from ADK
    warnings.filterwarnings("ignore", message=".*EXPERIMENTAL.*")

    # Suppress noisy third-party debug logs
    logging.getLogger("urllib3").setLevel(logging.INFO)
    logging.getLogger("googleapiclient").setLevel(logging.INFO)
    logging.getLogger("google_auth_httplib2").setLevel(logging.INFO)
    logging.getLogger("google.auth").setLevel(logging.INFO)
    logging.getLogger("google_adk").setLevel(logging.ERROR)
    logging.getLogger("httpcore").setLevel(logging.INFO)
    logging.getLogger("httpx").setLevel(logging.INFO)
    logging.getLogger("opentelemetry").setLevel(logging.INFO)
    logging.getLogger("mcp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.INFO)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
