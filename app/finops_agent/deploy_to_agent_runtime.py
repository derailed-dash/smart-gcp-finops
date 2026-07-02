import vertexai

from finops_agent.config import settings

# Verify required settings are populated
if not settings.google_cloud_project or not settings.google_cloud_region:
    raise ValueError("GOOGLE_CLOUD_PROJECT and GOOGLE_CLOUD_REGION settings must be configured.")

# Initialize the Vertex AI client
client = vertexai.Client(
    project=settings.google_cloud_project,
    location=settings.google_cloud_region,
    http_options={"api_version": "v1beta1"},
)


print(
    f"🤖 Deploying agent to project '{settings.google_cloud_project}' in region '{settings.google_cloud_region}'..."
)

remote_agent = client.agent_engines.create(
    config={
        "display_name": "FinSavant",
        "description": "Deploying FinSavant Agent to Agent Runtime.",
        "source_packages": ["finops_agent"],
        "entrypoint_module": "finops_agent.agent",
        "entrypoint_object": "root_agent",
        "requirements_file": "finops_agent/requirements.txt",
        "class_methods": [
            {
                "name": "ask",
                "api_mode": "",
                "parameters": {
                    "type": "object",
                    "properties": {"question": {"type": "string"}},
                    "required": ["question"],
                },
            },
        ],
        "service_account": f"smart-gcp-finops-app@{settings.google_cloud_project}.iam.gserviceaccount.com",
    }
)

print("✅ Agent successfully deployed!")
print(f"Resource Name: {remote_agent.resource_name}")
