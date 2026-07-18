# Technical Specification: FinSavant Multi-Agent Split

This specification defines the implementation details for splitting the monolithic FinSavant ADK agent into a coordinated multi-agent system.

---

## 1. Architectural Overview & References

We adopt a **Coordinator & Dispatcher** pattern at the root level. When complex investigations (such as cost spikes) are triggered, the coordinator delegates to a specialized subagent that handles multi-tool sequential or parallel analysis.

*   **Walkthrough Architecture**: Detailed in [docs/architecture-and-walkthrough.md](architecture-and-walkthrough.md#multi-agent-collaborative-architecture)
*   **ADK Collaboration Modes**: [ADK Collaborative Workflows](https://adk.dev/workflows/collaboration/index.md)
*   **ADK Workflow Patterns**: [ADK Workflow Patterns](https://adk.dev/workflows/patterns/index.md)
*   **ADK Plugins**: [ADK Plugins](https://adk.dev/plugins/index.md)
*   **Gemini Interactions API (Investigated & Incompatible)**: [ADK Gemini Models (Interactions API)](https://adk.dev/agents/models/google-gemini/index.md#gemini-interactions-api)
*   **Interactions API (Investigated & Incompatible)**: [Interactions API](https://ai.google.dev/gemini-api/docs/interactions-overview)
*   **Migrate to Interactions API (Investigated & Incompatible)**: [Migrate from generate_content to Interactions API](https://ai.google.dev/gemini-api/docs/migrate-to-interactions)

---

## 2. Decoupled Subagent Definitions

The system is split into one root coordinator and five specialized leaf subagents:

### 2.1 `FinOpsCoordinator` (Root)
*   **Description**: Receives all incoming user queries and routes them to the appropriate specialist.
*   **Mode**: Default (`chat`)
*   **Tools**: Exposes only the auto-generated subagent delegation tools. Has no direct BQ or CAI tools of its own.

### 2.2 `BillingExplorer`
*   **Mode**: `task` (can ask clarifying questions; automatically returns control via `finish_task`)
*   **Tools**: `execute_cached_bigquery_sql` and `BigQueryToolset`.
*   **Responsibilities**: Spend aggregation, SKU price analysis, MTD curves, and cost forecasting. Generates `explorer` and `dashboard` JSON+A2UI payloads.
*   **Instruction Focus**: Currency formatting, temporal scope precision (always stating duration/period), and strict caching of BQ query strings.

### 2.3 `InfrastructureAuditor`
*   **Mode**: `task`
*   **Tools**: `list_zombie_resources` and `get_cai_metadata_for_resources`.
*   **Responsibilities**: Auditing idle static IPs and unattached disks, and checking metadata states. Generates the `recommendations` A2UI payload.

### 2.4 `CloudAdvisor`
*   **Mode**: `task`
*   **Tools**: Gemini Cloud Assist tools (`ask_cloud_assist`).
*   **Responsibilities**: Real-time rightsizing and performance/cost optimization recommendations for active GCP resources.

### 2.5 `KnowledgeAssistant`
*   **Mode**: `single_turn` (no user interaction, immediate task exit)
*   **Tools**: Google Developer Knowledge MCP (`answer_query`, `search_documents`).
*   **Responsibilities**: Grounding cost optimization recommendations in official GCP architectural guidelines.

### 2.6 `RootCauseAnalyst`
*   **Mode**: `task`
*   **Tools**: `execute_cached_bigquery_sql` and `get_cai_history_for_resource`.
*   **Responsibilities**: Performs root cause analysis by matching BQ billing spike dates with CAI configuration change history logs to find cost drift.

---

## 3. Design Decision: Standard Inference vs. Interactions API

1.  **Interactions API Attempt**: We initially planned to use the cloud-managed Interactions API (`use_interactions_api=True`) on Vertex AI to leverage server-side conversation history and reduce network payload size.
2.  **Vertex AI Backend Limitation**: However, testing showed that the Vertex AI endpoint (`aiplatform.googleapis.com`) rejects raw text models (like `gemini-3.5-flash` or `gemini-2.5-flash`) on the Interactions API route, returning:
    ```json
    Error code: 400 - {'error': {'message': 'Unsupported model interaction: gemini-3.5-flash', 'code': 'invalid_request'}}
    ```
    The Vertex AI Interactions API is restricted to specific media models (`lyria-3-*`) and managed agents (`deep-research-*`).
3.  **Resolution**: We will adhere to standard stateless inference (`use_interactions_api=False`) and let the FastAPI BFF and ADK coordinate conversation history appending client-side. The existing unit test `tests/unit/test_interactions_api.py` enforces this constraint.

---

## 4. Test-Driven Development (TDD) Strategy

Before editing [agent.py](../agent/finops_agent/agent.py), create a new test file `tests/test_multiagent_split.py` to establish the contract:
*   **Router Mocking**: Mock the LLM's model calls to simulate routing from `FinOpsCoordinator` to `BillingExplorer` and `InfrastructureAuditor`.
*   **Session State Assertions**: Verify that subagents successfully write active services, allowed projects, and cost drivers to `session.state`.
*   **Modes & Handbacks**: Validate that `single_turn` subagents exit immediately with their result, and `task` subagents return control cleanly to the parent upon calling `finish_task`.

---

## 5. Observability, Logging, and Error Handling

*   **Global Logging via Plugins**: Rather than adding logging callbacks to every subagent, we write a custom `FinOpsTelemetryPlugin` subclassing `BasePlugin` and register it globally in the `App` plugins list. This plugin hooks into:
    *   `before_agent_callback` to log handoffs.
    *   `before_model_callback` to measure token consumption and monitor caching.
*   **Tool Error Resilience**: The existing `DefensiveToolErrorPlugin` will catch any unhandled tool exceptions across the subagents and store them in the state so that the coordinator's model bypass logic can present a clean user-facing alert without crashing the execution loop.
