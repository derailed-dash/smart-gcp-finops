"""Google Application Default Credentials (ADC) loader and helper utilities.

What:
    Provides functions to retrieve Google authentication credentials for Google Cloud client libraries.

Why:
    Centralizes credential resolution so all service clients (BigQuery, CAI, Billing) consistently use
    Application Default Credentials (ADC) in both local development and GCP runtime environments.

How:
    Calls ``google.auth.default()`` to fetch standard ADC credentials and handles quota project context.
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
