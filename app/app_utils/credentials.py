import logging

from google.auth import default
from google.auth.credentials import Credentials

from app.config import settings

logger = logging.getLogger(__name__)


def get_credentials() -> Credentials:
    """Loads default credentials and sets the quota project explicitly if supported.

    This avoids raising a TypeError due to 'quota_project_id' not being supported
    by google.auth.default.
    """
    credentials, _ = default()
    if hasattr(credentials, "with_quota_project"):
        credentials = credentials.with_quota_project(
            settings.google_cloud_billing_project
        )
    return credentials
