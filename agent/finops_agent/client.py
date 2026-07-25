"""
Description: Instantiates the shared, thread-safe GenAI Client and BigQuery toolsets.
Why: Prevents circular dependencies between the main orchestrator and the subagents.
How: Exports standard table IDs, ConfiguredGemini, and bigquery_toolset.
"""

import os
from typing import Any

import google.auth
from google.adk.integrations.bigquery import BigQueryCredentialsConfig, BigQueryToolset
from google.adk.models import Gemini
from google.genai import Client

from finops_agent.config import settings

# Ensure critical environment variables are set for the underlying SDKs
if settings.google_cloud_project:
    os.environ["GOOGLE_CLOUD_PROJECT"] = settings.google_cloud_project
if settings.google_cloud_region:
    os.environ["GOOGLE_CLOUD_REGION"] = settings.google_cloud_region
if settings.google_cloud_location:
    os.environ["GOOGLE_CLOUD_LOCATION"] = settings.google_cloud_location

os.environ["GOOGLE_GENAI_USE_VERTEXAI"] = str(settings.google_genai_use_vertexai)
if settings.gemini_api_key:
    os.environ["GEMINI_API_KEY"] = settings.gemini_api_key

if settings.google_cloud_billing_project:
    os.environ["GOOGLE_CLOUD_BILLING_PROJECT"] = settings.google_cloud_billing_project
if settings.billing_export_dataset:
    os.environ["BILLING_EXPORT_DATASET"] = settings.billing_export_dataset

billing_suffix = settings.google_cloud_billing_account.replace("-", "_")
standard_table_id = f"{settings.google_cloud_billing_project}.{settings.billing_export_dataset}.gcp_billing_export_v1_{billing_suffix}"
resource_table_id = f"{settings.google_cloud_billing_project}.{settings.billing_export_dataset}.gcp_billing_export_resource_v1_{billing_suffix}"

# Instantiate global, thread-safe GenAI Client at module level to reuse connection pools
genai_client = Client(
    vertexai=settings.google_genai_use_vertexai,
    location=settings.google_cloud_location,
    project=settings.google_cloud_project,
)


class ConfiguredGemini(Gemini):
    """A custom Gemini model wrapper that overrides default regional endpoint routing."""

    @property
    def api_client(self) -> Client:
        return genai_client


# Configure native BigQuery Toolset using Application Default Credentials (ADC)
credentials, _ = google.auth.default()
credentials_config = BigQueryCredentialsConfig(credentials=credentials)


EXCLUDED_BQ_TOOL_KEYWORDS = {"execute", "query", "forecast", "anomalies"}

def bq_tool_filter(tool: Any, ctx: Any = None) -> bool:
    """Excludes certain BigQuery tools from the exposed tool list to prevent bypass of custom tools."""
    name = tool.name.lower()
    return not any(keyword in name for keyword in EXCLUDED_BQ_TOOL_KEYWORDS)


bigquery_toolset = BigQueryToolset(
    credentials_config=credentials_config,
    tool_filter=bq_tool_filter,
)
