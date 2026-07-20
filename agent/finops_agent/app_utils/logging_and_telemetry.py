"""
Description: Logging and telemetry configuration for the application.
Why: Ensures consistent log configurations, warning filters, monitoring, and tracing.
How: Suppresses noisy third-party debug outputs and hooks OpenTelemetry to export to Cloud Trace / GCS.
"""

import logging
import os
import warnings

logger = logging.getLogger(__name__)


class SuppressMcpTracebackFilter(logging.Filter):
    """Custom filter to keep WARNING messages from MCP tool runner but suppress tracebacks."""

    def filter(self, record: logging.LogRecord) -> bool:
        if record.levelno < logging.ERROR:
            record.exc_info = None
            record.exc_text = None
        return True


def setup_telemetry() -> str | None:
    """Configure GenAI prompt/response logging via OpenTelemetry."""
    import google.auth
    from google.adk.cli.api_server import _setup_instrumentation_lib_if_installed
    from google.adk.telemetry.google_cloud import get_gcp_exporters, get_gcp_resource
    from google.adk.telemetry.setup import maybe_set_otel_providers

    os.environ.setdefault("ADK_CAPTURE_MESSAGE_CONTENT_IN_SPANS", "false")

    bucket = os.environ.get("LOGS_BUCKET_NAME")
    capture_content = os.environ.get("OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", "false")
    if bucket and capture_content != "false":
        logging.info(
            "Prompt-response logging enabled - mode: NO_CONTENT (metadata only, no prompts/responses)"
        )
        os.environ["OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"] = "NO_CONTENT"
        os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_UPLOAD_FORMAT", "jsonl")
        os.environ.setdefault("OTEL_INSTRUMENTATION_GENAI_COMPLETION_HOOK", "upload")
        os.environ.setdefault("OTEL_SEMCONV_STABILITY_OPT_IN", "gen_ai_latest_experimental")
        commit_sha = os.environ.get("COMMIT_SHA", "dev")
        os.environ.setdefault(
            "OTEL_RESOURCE_ATTRIBUTES",
            f"service.namespace=app,service.version={commit_sha}",
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

    try:
        credentials, project_id = google.auth.default()
        otel_hooks = get_gcp_exporters(
            enable_cloud_tracing=True,
            enable_cloud_metrics=False,
            enable_cloud_logging=True,
            google_auth=(credentials, project_id),
        )
        otel_resource = get_gcp_resource(project_id)
        maybe_set_otel_providers(
            otel_hooks_to_setup=[otel_hooks],
            otel_resource=otel_resource,
        )
    except Exception as e:
        logging.error("Failed to initialize standard ADK Telemetry: %s", e)

    try:
        _setup_instrumentation_lib_if_installed()
    except Exception as e:
        logging.warning("Failed to instrument Google GenAI SDK: %s", e)

    return bucket


def setup_logging_suppressions() -> None:
    """Configures Python logging levels and warning filters to suppress noisy third-party outputs."""
    warnings.filterwarnings("ignore", message=".*EXPERIMENTAL.*")
    warnings.filterwarnings(
        "ignore", message=".*httplib2 transport does not support per-request timeout.*"
    )

    logging.getLogger("urllib3").setLevel(logging.INFO)
    logging.getLogger("googleapiclient").setLevel(logging.INFO)
    logging.getLogger("google_auth_httplib2").setLevel(logging.INFO)
    logging.getLogger("google.auth").setLevel(logging.INFO)
    logging.getLogger("google.genai").setLevel(logging.WARNING)
    logging.getLogger("google_genai").setLevel(logging.WARNING)
    logging.getLogger("google_adk.google.adk.models").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    # logging.getLogger("opentelemetry").setLevel(logging.INFO)
    logging.getLogger("mcp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.INFO)
    logging.getLogger("uvicorn").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("watchdog").setLevel(logging.INFO)
    logging.getLogger("aiosqlite").setLevel(logging.INFO)

    mcp_filter = SuppressMcpTracebackFilter()
    for name in [
        "google_adk.google.adk.tools.mcp_tool.mcp_tool",
        "google_adk.google.adk.tools.mcp_tool.session_context",
    ]:
        lgr = logging.getLogger(name)
        lgr.setLevel(logging.WARNING)
        if not any(isinstance(f, SuppressMcpTracebackFilter) for f in lgr.filters):
            lgr.addFilter(mcp_filter)
