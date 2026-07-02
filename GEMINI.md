# Project Goals

To create an agentic FinOps solution for GCP that:

- Uses ADK for agent orchestration.
- Is able to examine billing and cost data in BigQuery, leveraging Google remote BigQuery MCP
- Is able to understand Google Cloud infrasture and services across multiple Google projects, leveraging Google Developer Knowledge API MCP.
  - Consider projects associated with a particular billing account.
  - Consider projects associated with a particular Google Cloud organisation.
- Is able to detect cost anomalies and inefficiencies, and trends.
- Is able to understand all deployed infra and services, leveraging Google Cloud Asset Inventory
- Is able to combine all of the above to provide actionable insights and recommendations to users.
- Provides a UI for users, which includes:
  - Dashboard of cost trends, billing data and anomalies
  - Cost forecasting
  - Cost analysis
  - Anomaly detection
  - Recommendations
  - Cost optimisation suggestions
  - A natural language chat interface
- The UI should be based on React. Use skills you have available to leverage React best practices.
- Leverage Stitch to build the UI, and use the Stitch MCP server (if available) for this purpose.
- The UI is connected to the agent via FastAPI.
- The UI and backend are hosted in a single Cloud Run service.
- The UI and backend are secured using IAP, enabled on Cloud Run (not via a Load Balancer)

## Tool Use: Skills, Gemini Enterprise Agent Platform, Agent Runtime and ADK

Be sure to use all agents skills, Gemini Enterprise Agent Platform skills, and ADK skills you have available for developing ADK agents and best practices, and use adk-docs-mcp for latest documentation. These skills will be listed here for convenience.

### ADK & agents-cli Lifecycle Skills

- `google-agents-cli-workflow`: Entrypoint for building ADK agents (scaffold, build, evaluate, deploy, publish, observe).
- `google-agents-cli-scaffold`: Creating and upgrading agent projects (agents-cli scaffold create/enhance/upgrade).
- `google-agents-cli-adk-code`: Agent Development Kit (ADK) Python API patterns, tool definitions, callbacks, and state management.
- `google-agents-cli-deploy`: Configuring and executing deployments to Agent Runtime, Cloud Run, or GKE.
- `google-agents-cli-eval`: Running agent evaluations and understanding the Agent Platform Quality Flywheel.
- `google-agents-cli-observability`: Monitoring, tracing, and logging deployed ADK agents in production.
- `google-agents-cli-publish`: Registering and publishing ADK agents to the Gemini Enterprise / Agent Registry.

### Gemini Enterprise Agent Platform APIs

- `gemini-api`: Vertex AI, Google Cloud, and Agent Platform enterprise usage with the Google Gen AI SDK.
- `gemini-agents-api / gemini-managed-agents-api`: Creating, configuring, and managing custom Agent resources programmatically.
- `gemini-interactions-api`: Stateful, server-managed multi-turn conversation and function execution workflows.

### Agent Platform Engine & Model Management

- `agent-platform-deploy`: Deploying models and tuned weights to Agent Platform endpoints.
- `agent-platform-model-registry`: Uploading, versioning, and managing models in the Agent Platform Model Registry.
- `agent-platform-prompt-management`: Managing and versioning system/agent prompts.
- `agent-platform-rag-engine-management`: Managing RAG Engine Corpora and retrieving grounded contexts.
- `agent-platform-skill-registry`: Integrating and searching for registered agent skills.
- `agent-platform-tuning`: Fine-tuning models on Agent Platform infrastructure.
- `agent-platform-tuning-management`: Managing GenAI tuning jobs (listing, checking, cancelling).

### Other Guides for Deploying to Agent Runtime

See:
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk
- https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/deploy-an-agent#from-source-files
- https://adk.dev/deploy/agent-runtime/
- https://adk.dev/deploy/agent-runtime/deploy/


## ADK + React UI Best Practices

- **Architecture**: Use the **Unified Container** pattern (React + FastAPI + ADK) for Cloud Run deployments to simplify CORS and authentication (IAP).
- **Backend for Frontend (BFF)**: Use FastAPI as a thin layer to serve static React assets and provide a robust API for the ADK agent.
- **Rich UI (A2UI)**: Leverage the **Agent-to-UI (A2UI)** protocol for structured data outputs. The agent should return `application/json+a2ui` payloads for complex components like tables, charts, and cards.
- **UI Acceleration**: Use **Stitch with MCP** to rapidly build and iterate on information-dense dashboards.

## Key Internal Documentation

- TODO.md - High level plan for the project
- README.md - Project README
- docs/blog.md - A blog post document we will build along the way
- /deployment/README.md - Deployment documentation

## Essential Reading

You should read and leverage these resources for guidance and best practices, in addition to the skills and MCP servers you have available for knowledge.

| Resource | Description and Relevance |
| -------- | ------------------------- |
| https://docs.cloud.google.com/bigquery/docs/use-bigquery-mcp | Use the BigQuery MCP server | 
| https://adk.dev/integrations/bigquery/ | BigQuery tool for ADK |
| https://docs.cloud.google.com/gemini-enterprise-agent-platform | Gemini Enterprise Agent Platform Overview |
| https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/observability/overview | Gemini Enterprise Agent Platform - Observability Overview |
| https://docs.cloud.google.com/asset-inventory/docs/asset-inventory-overview | Google Cloud Asset Inventory overview. This provides an overview of Google Cloud Asset Inventory, and how to use it. |
| https://docs.cloud.google.com/asset-inventory/docs/list-assets | List assets. This gives instructions for how to list assets using Google Cloud Asset Inventory. |

## Other Notes

- "Vertex AI" is no more; the replacement is Gemini Enterprise Agent Platform.
- "Vertex AI Agent Engine" is no more; the replacement is "Agent Runtime", which is a part of the Gemini Enterprise Agent Platform.

## Blog

I want to build a multi-part blog series, which I'll post on Medium and Dev.to.

### Documenting As We Go

As we go, document steps taken, experience and findings in docs/blog.md. Later, I will build a Medium blog from this content. During this "as we go" phase, the blog.md does not need to be a polished article. It can be a collection of notes, code snippets, and observations. It should:

- Include all the key steps we did, in the order we did them.
- Capture notes / deep dives on these steps, any problems we faced, any lessons learned.
- The deep dives should be comprehensive and detailed, and should include code snippets, screenshots, and other relevant information.
- The deep dives should be added in the same sequence as the steps we took.

You should update the `blog.md` after any significant investigations, changes or features.

### Creating the Blog Articles

The series should have several parts. I'm thinking:

- 1. Overall Series Goals & Design
  - The goals of the project
  - The overall architecture
  - The technology stack
  - The design decisions and rationale
  - Which APIs and MCPs we've used, and why
  - What other APIs and MCPs could we have used?

- 2. Building the Agentic Solution
  - Local Dev Environment
  - Use of Agy IDE, and Agy CLI
  - MCPs and skills we've used for development
  - Use of ADK
  - Bootstrapping with Agents CLI
  - Implementation of agents
  - How the agent uses MCP and tools
  - Any patterns we've used

- 3. Building the UI, using A2UI

- 4. Deployment, Authentication, Terraform, CI/CD

- 5. Observability, Evaluation, and Tuning with Gemini Enterprise Agent Platform

Each part will be drafted in a separate md file under docs/blog. We're going to document in Dazbo style, but don't overdo the character. Subtle Dazbo.
