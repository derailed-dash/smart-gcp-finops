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

## Tool Use

Be sure to use all adk skills you have available for developing ADK agents and best practices, and use adk-docs-mcp for latest documentation.

## ADK + React UI Best Practices

- **Architecture**: Use the **Unified Container** pattern (React + FastAPI + ADK) for Cloud Run deployments to simplify CORS and authentication (IAP).
- **Backend for Frontend (BFF)**: Use FastAPI as a thin layer to serve static React assets and provide a robust API for the ADK agent.
- **Rich UI (A2UI)**: Leverage the **Agent-to-UI (A2UI)** protocol for structured data outputs. The agent should return `application/json+a2ui` payloads for complex components like tables, charts, and cards.
- **Streaming & UX**: Use **Server-Sent Events (SSE)** for all chat interactions. Implement a **heartbeat mechanism** (e.g., sending whitespace or comments every 15s) to prevent Cloud Run timeouts during long agent operations.
- **State Synchronization**: Use **AG-UI** patterns for bi-directional state sharing between the UI and the agent when building complex interactive features.
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
| https://cloud.google.com/blog/topics/developers-practitioners/build-a-multi-agent-system-for-expert-content-with-google-adk-mcp-and-cloud-run-part-1?e=48754805 | Build a multi-agent system for expert content with Google ADK, MCP, and Cloud Run (Part 1). This gives instructions for how to build a multi-agent system using ADK and Cloud Run, and which leverages Google Developer Knowledge API MCP. |
| https://medium.com/google-cloud/tutorial-getting-started-with-google-mcp-services-60b23b22a0e7 | Tutorial: Getting started with Google MCP services. This gives instructions for how to use Google MCP services. |
| https://docs.cloud.google.com/bigquery/docs/use-bigquery-mcp | Use the BigQuery MCP server | 
| https://adk.dev/integrations/bigquery/ | BigQuery tool for ADK |
| https://developers.google.com/knowledge/mcp | Google Developer Knowledge API MCP. This MCP server provides access to Google Cloud documentation and best practices. This document describes how to use it. |
| https://docs.cloud.google.com/gemini-enterprise-agent-platform | Gemini Enterprise Agent Platform Overview |
| https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/observability/overview | Gemini Enterprise Agent Platform - Observability Overview |
| https://developers.googleblog.com/agents-cli-in-agent-platform-create-to-production-in-one-cli/ | Agents CLI - for bootstrapping your ADK agent | 
| https://dev.to/gde/beyond-dashboards-architecting-a-genai-finops-analyst-using-bigquery-native-mcp-48jc | Beyond Dashboards: Architecting a GenAI FinOps Analyst using BigQuery Native MCP. This gives instructions for how to build a FinOps analyst using ADK and Cloud Run, and which leverages Google Developer Knowledge API MCP. |
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