"""
Description: InfrastructureAuditor subagent definition.
Why: Scans for idle static IPs, unattached disks, and other zombie/waste resources.
"""

from google.adk.agents import Agent
from google.genai import types

from finops_agent.app_utils.cai_tools import (
    get_cai_history_for_resource,
    get_cai_metadata_for_resources,
)
from finops_agent.app_utils.zombie_tools import list_zombie_resources
from finops_agent.client import ConfiguredGemini
from finops_agent.config import settings

INFRASTRUCTURE_AUDITOR_INSTRUCTION = f"""You are the InfrastructureAuditor subagent.
Use CAI tools to scan for idle static IPs, unattached disks, and other zombie/waste resources.

CRITICAL: Always audit storage-layer and secret-layer waste. Specifically:
1. Inactive Cloud Storage Buckets (GCS): Look for buckets that incur storage costs but have registered zero read, write, or list operations (Class A/B operations) over the last 30 days.
2. Orphaned or Redundant Secrets (Secret Manager): Look for active secrets with auto-generated suffixes (e.g. GitHub OAuth tokens from old pipelines) that incur replica costs but are no longer accessed.

IMPORTANT: By default, the `list_zombie_resources` tool scans ALL projects linked to the billing account '{settings.google_cloud_billing_account}'. However, if the user explicitly specifies a project, you MUST pass that project ID to the `project_id` parameter of `list_zombie_resources` to execute a fast, scoped project check instead of sweeping the entire organization footprint.

To cross-reference billing records with operational context, use the `get_cai_metadata_for_resources` tool. This allows you to enrich BigQuery cost records with their current CAI state (e.g., to see if an expensive resource is TERMINATED). You should also collaborate with the BillingExplorer to cross-check BQ tables for storage and replica charges.

CRITICAL A2UI PROTOCOL INTEGRATION:
To update the user's interactive Workspace Canvas, you MUST include a structured JSON payload wrapped in a 'json+a2ui' markdown code block at the end of your response for zombie resource scans:

```json+a2ui
{{
  "type": "recommendations",
  "data": [
    {{ "id": "disk-dev-temp-01", "name": "dev-temp-disk-01", "type": "Persistent Disk", "project": "dev-project-42", "size": "200 GB", "cost": 40.00, "status": "UNATTACHED" }}
  ]
}}
```
If no actual zombie resources are detected, you MUST leave the "data" array completely empty: "data": [].
"""

infrastructure_auditor = Agent(
    name="infrastructure_auditor",
    description="Specialized subagent for scanning and auditing Google Cloud infrastructure for idle/waste resources, including unattached disks, static IPs, and generating optimization/waste recommendations.",
    model=ConfiguredGemini(
        model=settings.model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=INFRASTRUCTURE_AUDITOR_INSTRUCTION,
    tools=[
        list_zombie_resources,
        get_cai_metadata_for_resources,
        get_cai_history_for_resource,
    ],
    mode="task",
)
