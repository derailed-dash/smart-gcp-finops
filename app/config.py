"""
Description: Application configuration settings.
Why: Centralizes settings from environment variables for consistent configuration across the app.
How: Uses `pydantic-settings` to load and validate environment variables.

Configuration Sources:
1. Environment Variables: In production (Cloud Run), settings are injected as environment variables.
2. .env File: For local development, settings are loaded from a `.env` file in the project root.

Usage:
    from app.config import settings
    print(settings.google_cloud_project)
"""

import os

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application settings model.

    Fields defined here are automatically populated from environment variables
    (case-insensitive) or the .env file.
    """

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


settings = Settings()  # ty: ignore[missing-argument]
