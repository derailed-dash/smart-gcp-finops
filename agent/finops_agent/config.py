"""
Description: Application configuration settings.
Why: Centralizes settings from environment variables for consistent configuration across the app.
How: Uses `pydantic-settings` to load and validate environment variables.
"""

import os
from typing import Any

from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings model.

    Fields defined here are automatically populated from environment variables
    (case-insensitive) or the .env file.
    """

    @model_validator(mode="before")
    @classmethod
    def strip_outer_quotes(cls, data: Any) -> Any:
        """Strip outer quotes from string values to handle environment variables

        exported by Makefiles or other wrappers that preserve quotes.
        """
        if isinstance(data, dict):
            cleaned = {}
            for k, v in data.items():
                if isinstance(v, str):
                    if (v.startswith('"') and v.endswith('"')) or (
                        v.startswith("'") and v.endswith("'")
                    ):
                        v = v[1:-1]
                cleaned[k] = v
            return cleaned
        return data

    model_config = SettingsConfigDict(
        env_file=".env" if not os.getenv("CI") else None,
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Google Project Infrastructure
    google_cloud_project: str = ""
    google_cloud_region: str = ""

    # GenAI / Vertex AI Configuration
    # These are often used by the underlying Google SDKs
    google_genai_use_vertexai: bool = True
    google_cloud_location: str = "global"  # Used by Gemini model
    gemini_api_key: str | None = None  # Used when google_genai_use_vertexai is False

    # Billing
    google_cloud_billing_account: str = ""
    google_cloud_billing_location: str = ""
    google_cloud_billing_project: str = ""
    billing_export_dataset: str = "all_billing_data"

    # Infrastructure Scope (Optional)
    google_cloud_organization: str | None = None

    # Agent
    app_name: str = "smart_gcp_finops"  # must use underscores, not hyphens
    log_level: str = "INFO"
    model: str = "gemini-3.5-flash"
    fast_model: str = "gemini-3.1-flash-lite"
    local_developer_email: str = "local-dev@example.com"
    playground_service_identity: str = "vais-query-reasoning-engine"  # Identity used by the GCP Console Playground to query reasoning engines; used to apply restricted project scoping defensively

    # Rate Limiting Configuration
    dashboard_rate_limit: str = "10/minute; 100/day"
    chat_rate_limit: str = "5/minute; 100/day"
    feedback_rate_limit: str = "20/minute; 500/day"


settings = Settings()
