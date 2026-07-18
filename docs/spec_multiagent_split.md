# Technical Specification: FinSavant Multi-Agent Split

This specification defines the implementation details for splitting the monolithic FinSavant ADK agent into a coordinated multi-agent system.

---

## 1. Architectural Overview & References

We adopt a **Coordinator & Dispatcher** pattern at the root level. When complex investigations (such as cost spikes) are triggered, the coordinator delegates to a specialized subagent that handles multi-tool sequential or parallel analysis.

*   **Walkthrough Architecture**: Detailed in [docs/architecture-and-walkthrough.md](architecture-and-walkthrough.md#multi-agent-collaborative-architecture)
*   **Walkthrough Architecture**: Detailed in [docs/architecture-and-walkthrough.md](file:///home/dazbo/localdev/smart-gcp-finops/docs/architecture-and-walkthrough.md#multi-agent-collaborative-architecture)
*   **ADK Collaboration Modes**: [ADK Collaborative Workflows](https://adk.dev/workflows/collaboration/index.md)
*   **ADK Workflow Patterns**: [ADK Workflow Patterns](https://adk.dev/workflows/patterns/index.md)
*   **ADK Plugins**: [ADK Plugins](https://adk.dev/plugins/index.md)
*   **Gemini Interactions API**: [ADK Gemini Models (Interactions API)](https://adk.dev/agents/models/google-gemini/index.md#gemini-interactions-api)

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

## 3. Stateful Optimization & Interactions API

To comply with the rule of **minimizing latency** and **limiting high token usage**:
1.  **Interactions API**: Enable `use_interactions_api=True` on the Gemini model configuration inside [agent.py](file:///home/dazbo/localdev/smart-gcp-finops/agent/finops_agent/agent.py).
2.  **BFF Payload Optimization**: Since the session is held statefully server-side via the model's `interaction_id`, the FastAPI BFF must be refactored to send **only the new user message and the `session_id`** on each turn. Sending the full conversation history array over the network is completely disabled.

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
