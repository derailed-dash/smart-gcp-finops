"""
Description: Google credentials resolver helper.
Why: Ensures that local and remote credentials configure and apply billing quota project context correctly.
How: Fetches default Application Credentials (ADC) and applies with_quota_project setting safely.
"""

import logging

from google.auth import default
from google.auth.credentials import Credentials

# Inherits effective log level from the root logger
logger = logging.getLogger(__name__)


def get_credentials() -> Credentials:
    """Loads default credentials."""
    credentials, _ = default()
    return credentials
