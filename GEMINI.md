# FinSavant

## Project Goals

To create an agentic FinOps solution for GCP that:

- Uses ADK for agent orchestration.
- Is able to examine billing and cost data in BigQuery, based on billing exports.
- Is able to understand Google Cloud infrasture and services across multiple Google projects associated with a billing account.
- Considers projects associated with a particular Google Cloud organisation, associated with a billing account.
- Leverages Google Developer Knowledge API MCP for grounding:  Google APIs, Google Cloud infrastructure, Google Cloud best practices.
- Is able to detect cost anomalies and inefficiencies, and trends.
- Is able to understand all deployed infra and services, and historical configuration changes, leveraging Google Cloud Asset Inventory
- Is able to invoke Google Cloud Assist for immediate logs investigation, RCA and recommendations.
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
- Leverage Google Stitch to design the UI, and use the Stitch MCP server to pull in the design, in order to convert to React.
- The UI is connected to the agent via FastAPI.
- The UI and API will be hosted in a single Cloud Run service. The service will be secured using IAP, using direct Cloud Run integration - no Load Balancer.
- The Agent will be deployed to Agent Runtime in Gemini Enteprise Agent Platform.

## Tool Use: Skills, Gemini Enterprise Agent Platform, Agent Runtime and ADK

Be sure to use all **agents** skills, **Gemini Enterprise Agent Platform** skills, and **ADK** skills you have available for developing ADK agents and best practices, and use **adk-docs-mcp** for latest ADK documentation. 

You will have additional skills available to you, but always check if the following can help with a particular task.

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

## ADK + React UI Best Practices

- **Backend for Frontend (BFF)**: Use FastAPI as a thin layer to serve static React assets and provide a robust API for the ADK agent.
- **Rich UI (A2UI)**: Leverage the **Agent-to-UI (A2UI)** protocol for structured data outputs. The agent should return `application/json+a2ui` payloads for complex components like tables, charts, and cards.
- **UI Acceleration**: Use **Stitch with MCP** to rapidly build and iterate on information-dense dashboards.

## Key Internal Documentation

- README.md - Project README; the developer's front door
- TODO.md - High level plan for the project
- PRD.md - The product spec
- architecture-and-walkthrough.md - The main architecture, including design decisions
- DESIGN.md - Where we will capture the UI design
- testing.md - Where we will document test strategy, summary of tests, testing instructions, any manual testing processes
- docs/blog.md - A blog post document we will build along the way
- /deployment/README.md - Deployment and CI/CD documentation

## Essential Reading

You should read and leverage these resources for guidance and best practices, in addition to the skills and MCP servers you have available for knowledge.

| Resource | Description and Relevance |
| -------- | ------------------------- |
| https://docs.cloud.google.com/bigquery/docs/use-bigquery-mcp | Use the BigQuery MCP server | 
| https://adk.dev/integrations/bigquery/ | BigQuery tool for ADK |
| https://docs.cloud.google.com/gemini-enterprise-agent-platform | Gemini Enterprise Agent Platform Overview |
| https://adk.dev/deploy/agent-runtime | ADK with Agent Runtime |
| https://adk.dev/deploy/agent-runtime/deploy/ | Deploying ADK agents to Agent Runtime |
| https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime/quickstart-adk | Agent Runtime Quickstart |
| https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/runtime/deploy-an-agent#from-source-files | Deploying to Agent Runtime |
| https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/observability/overview | Gemini Enterprise Agent Platform - Observability Overview |
| https://docs.cloud.google.com/asset-inventory/docs/asset-inventory-overview | Google Cloud Asset Inventory overview. This provides an overview of Google Cloud Asset Inventory, and how to use it. |
| https://docs.cloud.google.com/asset-inventory/docs/list-assets | List assets. This gives instructions for how to list assets using Google Cloud Asset Inventory. |

## Other Notes

- "Vertex AI" no longer exists as a product; the replacement is Gemini Enterprise Agent Platform.
- "Vertex AI Agent Engine" is no more; the replacement is "Agent Runtime", which is a part of the Gemini Enterprise Agent Platform.
- But APIs and Google internal resource names may still refer to legacy names, e.g. `reasoningEngine` rather than Agent Runtime. Always use the new names when creating documentation, but be mindful that we may need to use old names in API calls and certain resource definitions.

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

- 2. Setting up Our Dev Environment
  - Local Dev Environment
  - Use of Agy IDE, and Agy CLI
  - MCPs and skills we've used for development
  - Bootstrapping with Agents CLI
  - Validation with ADK Web
  - Creating a Makefile

- 3. Building the Agent and API
  - Implementation
  - How the agent uses MCP and tools
  - Any patterns we've used
  - Validating with ADK Web
  - Testing the API

- 4. Building the UI with Stitch and A2UI
  - Designing with Stitch
  - Integrating Stitch with MCP
  - A2UI for the Dynamic UI
  - Rendering A2UI from React
  - Testing the UI

- 5. Deployment, Runtimes, Authentication
  - Container images for Agent, and for UI/BFF
  - Deploying Agent to GEAP Agent Runtime
  - Looking at GEAP: Agent Registry, Playground
  - Deploying UI/BFF to Cloud Run
  - Getting Them Talking

- 6. Setting up Terraform, GitOps and CI/CD
  - Terraform for infra
  - CI/CD pipeline with GH Actions
  - Automated PR Reviews with Gemini

- 7. Agent Observability, Evaluation, and Tuning with Gemini Enterprise Agent Platform

Each part will be drafted in a separate md file under docs/blog. We're going to document in Dazbo style, but don't overdo the character. Subtle Dazbo.
