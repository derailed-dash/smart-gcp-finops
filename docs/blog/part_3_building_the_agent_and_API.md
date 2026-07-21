# Building the Multi-Agent FinOps Solution with ADK

## Welcome Back!

We're continuing our _FinSavant_ series. In the previous two parts we:

1. Looked at the overall goals and architecture
2. Setup our development environment, fully loaded with MCP servers and agent skills

In this part we're going to take a close look at the agent code. We'll be looking at:

- The various agents that make up the solution, and their tools.
- Different multi-agent orchestration patterns, and the pattern we selected for _FinSavant_.
- How we handle cross-cutting concerns across agents.
- Testing with `ADK web`
- Optimisation
- Unit testing
- Building a FastAPI _Backend-for-Frontend_
- Creating and running a local Docker container

Let's get cracking!

## Series Orientation

First, a quick reminder of where we are in the series:

1. [Goals, Architecture, and Tech Stack: Capabilities, project goals, target architecture, technology stack, and design decisions.](https://medium.com/google-cloud/finsavant-part-1-building-an-agentic-finops-platform-with-google-adk-a2ui-and-gemini-enterprise-248f59cea3a0?postPublishedType=repub)
2. [Dev Environment Setup with Google Antigravity, ADK, Agents CLI, MCP & Skills](https://medium.com/google-cloud/finsavant-part-2-building-an-agentic-finops-platform-development-environment-setup-google-dd12b8b84ba0)
3. **Building the ADK Agent and API 📍 You are here.**
4. Designing and Building the UI with Google Stitch and A2UI
5. Deployment with Gemini Enterprise Agent Platform, Agent Runtime, Cloud Run and IAP
6. Automating Deployment with CI/CD and Terraform
7. Agent Observability, Evaluation, and Tuning with Gemini Enterprise Agent Platform

## Deciding on Our Agents

_FinSavant_ is a FinOps solution that needs to do many different things. We could have one giant agent with a huge monolithic prompt. But this is an antipattern because:

- The prompt becomes unwieldy.
- It's too complicated to manage the possible journeys and workflows the prompt needs to manage.
- The agent is more likely to not follow the rules.
- We would have to give our single agent access to many tools, which can lead to the agent getting confused as to which tool it should use.
- The agent is ultimately less reliable and less consistent.

A much better approach is to have individual agents that each have a clear purpose, and which each have a limited set of tools they can use. We can then have a root agent that orchestrates the agents and decides which agent to use for each task.

Something like this:

![Multi-agent design](../images/illustrated_agent_architecture.png)

## Agent Directory Structure

Let's deep-dive on the `/agent` directory:

```text
smart-gcp-finops/
├── agent/                     # Core ADK Agent & Agent Runtime package
│   ├── finops_agent/
│   │   ├── agents/            # Subagent definitions
│   │   │   ├── billing_explorer_agent.py
│   │   │   ├── cloud_advisor_agent.py
│   │   │   ├── infrastructure_auditor_agent.py
│   │   │   ├── knowledge_assistant_agent.py
│   │   │   └── root_cause_analyst_agent.py
│   │   ├── app_utils/         # Shared tools and utilities
│   │   │   ├── a2a.py
│   │   │   ├── cai_tools.py
│   │   │   ├── cai_utils.py
│   │   │   ├── context.py
│   │   │   ├── credentials.py
│   │   │   └── etc
│   │   ├── agent.py           # Root agent
│   │   ├── callbacks.py       # Global callbacks
│   │   ├── client.py          # Gemini & MCP client initialisation
│   │   └── config.py          # Agent config
│   └── pyproject.toml         # Agent package dependencies
├── bff/                       # Backend-for-Frontend FastAPI service
├── docs/                      # Documentation
├── frontend/                  # React UI
├── scripts/                   # Helper & environment scripts
├── tests/                     # Unit & integration test suites
├── Dockerfile                 # Unified dev container build
├── Makefile                   # Development & deployment convenience
└── pyproject.toml             # Root workspace dependencies
```

You might be wondering about the directory naming here — why do we have `agent/`, then `finops_agent/`, and then `agents/`? 

It might look a bit repetitive at first glance, but there's clear structural logic behind it:

1. **`agent/` (Component Directory)**: This is our top-level monorepo component folder, sitting alongside `/bff`, `/frontend`, and `/deployment`. It houses all build manifests (`pyproject.toml`, `Dockerfile`) and dependencies specific to the agent backend. This will be important later when we deploy to the Agent Runtime.
2. **`finops_agent/` (Python Package)**: This is the actual Python package directory. By using a distinct package name rather than `agent`, we avoid Python module name collisions and allow clean, explicit imports (e.g. `from finops_agent.agent import root_agent`). This is also the standard layout expected by ADK's `agents-cli` tooling.
3. **`agents/` (Subagent Module)**: This nested directory houses our individual subagent definitions (`billing_explorer_agent.py`, `cloud_advisor_agent.py`, etc.). Separating them into their own module keeps the subagents isolated from the root coordinator (`agent.py`), global callbacks (`callbacks.py`), and utilities (`app_utils/`).

## The Specialized Agents & Their Tools

With our directory structure in place, let's look at each of our agents in detail:

### 1. `FinOpsCoordinator` (Root Agent)

- **Name**: Serves as the central router and front door for all user queries.
- **Model**: `gemini-3.1-flash-lite`.
- **Tools**: Exposes **zero direct tools** (no SQL or Cloud Asset Inventory access). Its sole capability is delegating to specialized subagents using ADK's native agent routing mechanisms.
- **Selective Routing Rules**: Prompt instructions strictly enforce selective delegation. For example, if the user asks solely about costs, it delegates exclusively to `BillingExplorer`, avoiding wasteful multi-agent sweeps.

Here's a snippet of the code:

```python
AGENT_INSTRUCTION = """You are the FinOpsCoordinator root agent.
Your primary role is to receive user requests, understand their intent, and delegate cost analysis, auditing, optimization, and Q&A tasks to the appropriate specialist subagents:

1. BillingExplorer: Use for spend aggregates, SKU prices, cost trends, forecasting, and Cost Explorer (explorer/dashboard) dashboards.
2. InfrastructureAuditor: Use for auditing zombie resources like idle static IPs or unattached disks (recommendations dashboard).
3. CloudAdvisor: Use for active GCP rightsizing and resource-level cost/performance optimizations.
4. KnowledgeAssistant: Use for general GCP Q&A and grounding recommendations in official architectural guidelines.
5. RootCauseAnalyst: Use for analyzing cost spikes by correlating BigQuery spend shifts with CAI configuration change history.

CRITICAL SELECTIVE ROUTING RULES:
1. You MUST only delegate tasks to the specific subagent(s) directly relevant to the user's request.
   - If the user only asks about costs, spend trends, SKU prices, or budgets, ONLY invoke BillingExplorer. Do NOT invoke CloudAdvisor or InfrastructureAuditor.
   - If the user only asks about rightsizing, active recommendations, or optimizations, ONLY invoke CloudAdvisor.
   - If the user only asks about zombie resources, idle IPs, or unattached disks, ONLY invoke InfrastructureAuditor.
2. Do NOT run a full multi-agent audit (calling multiple subagents) unless the user explicitly requests a "full audit", "comprehensive review", "complete environment analysis", or asks a multi-faceted question that spans multiple domains. Keep simple queries fast and single-scoped!
"""

root_agent = Agent(
    name="root_agent",
    model=ConfiguredGemini(
        model=settings.fast_model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=AGENT_INSTRUCTION,
    tools=[],
    sub_agents=[
        billing_explorer,
        infrastructure_auditor,
        cloud_advisor,
        knowledge_assistant,
        root_cause_analyst,
    ],
    before_agent_callback=[
        clean_history_callback,
        reset_tool_call_counter,
        discover_projects_callback,
        before_agent_cache_lookup,
    ],
    before_tool_callback=check_tool_call_limit,
    before_model_callback=before_model_bypass,
    after_agent_callback=after_agent_save_cache,
)

app = App(
    root_agent=root_agent,
    name="finops_agent",
    context_cache_config=ContextCacheConfig(
        min_tokens=2048,  # Trigger caching for large prompts/histories
        ttl_seconds=600,  # Store the cache for up to 10 minutes
        cache_intervals=10,  # Refresh after 10 turns
    ),
    plugins=[DefensiveToolErrorPlugin(), FinOpsTelemetryPlugin()],
)
```

### 2. `BillingExplorer` (Spend Aggregation & Dashboards)

- **Model**: `gemini-3.5-flash`.
- **Tools**: `get_precomputed_spend_analysis`, `execute_cached_bigquery_sql`, native `BigQueryToolset`, `get_session_value`, `set_session_value`.
- **Responsibilities**: Aggregates Month-to-Date (MTD) spend, analyzes SKU costs, forecasts end-of-month spend, and constructs structured `explorer` and `dashboard` JSON+A2UI payloads for the React canvas. (More on that in a later part, naturally!)

```python
from finops_agent.app_utils.tools import (
    BLACKBOARD_KEY_INSTRUCTIONS,
    execute_cached_bigquery_sql,
    get_precomputed_spend_analysis,
    get_session_value,
    set_session_value,
)
from finops_agent.client import (
    ConfiguredGemini,
    bigquery_toolset,
)
from finops_agent.config import settings

BILLING_EXPLORER_INSTRUCTION = """You are the BillingExplorer subagent.
Use the `get_precomputed_spend_analysis` tool to retrieve pre-computed Month-to-Date (MTD) cloud costs, period-over-period trends, cost drivers, and Secret Manager/GCS zombie waste metrics.
Do NOT attempt to run standard SQL queries or other cache functions directly if `get_precomputed_spend_analysis` is available, as it provides pre-aggregated and filtered cost results in a single call.

< trimmed for readabilty >

CRITICAL: CONCISE SYNTHESIS RULE
Write your report in a highly concise style. Keep the markdown text under 250 words total.

CRITICAL COORDINATION AND TERMINATION RULES:
1. Call `finish_task` and pass the complete final markdown report directly into the `result` parameter.
2. Once you have generated the report and returned it via `finish_task`, stop execution.
"""

billing_explorer = Agent(
    name="billing_explorer",
    description="Specialized subagent for querying Standard and Resource-level billing tables, summarizing Month-to-Date (MTD) cloud costs, forecasting future spend, identifying top cost drivers, and generating Cost Explorer (explorer/dashboard) workspaces.",
    model=ConfiguredGemini(
        model=settings.model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=BILLING_EXPLORER_INSTRUCTION + BLACKBOARD_KEY_INSTRUCTIONS,
    tools=[
        get_precomputed_spend_analysis,
        execute_cached_bigquery_sql,
        bigquery_toolset,
        get_session_value,
        set_session_value,
    ],
    mode="task",
)
```

### 3. `InfrastructureAuditor` (Waste & Zombie Resource Auditing)

- **Model**: `gemini-3.5-flash`.
- **Tools**: `list_zombie_resources`, `get_precomputed_spend_analysis`, `get_cai_metadata_for_resources`, `get_cai_history_for_resource`.
- **Responsibilities**: Scans for unattached Persistent Disks, idle static external IP addresses, inactive GCS storage buckets, and orphaned Secret Manager secrets. Generates `recommendations` JSON+A2UI payloads.

### 4. `CloudAdvisor` (Cloud-Assist Insights)

- **Model**: `gemini-3.1-flash-lite`.
- **Tools**: `ask_cloud_assist` (via Gemini Cloud Assist MCP), `get_session_value`.
- **Responsibilities**: Retrieves active GCP rightsizing and performance optimization recommendations for deployed resources.

### 5. `KnowledgeAssistant` (Architectural Grounding RAG)

- **Model**: `gemini-3.1-flash-lite`.
- **Tools**: `dev_knowledge_mcp_toolset` (Google Developer Knowledge MCP: `answer_query`, `search_documents`).
- **Responsibilities**: Grounds cost optimisation and architecture advice directly in official Google Cloud developer and architecture framework documentation, returning authoritative citations.

```python
KNOWLEDGE_ASSISTANT_INSTRUCTION = """You are the KnowledgeAssistant subagent.
Query the Developer Knowledge MCP to retrieve and ground cost optimization recommendations in official GCP architectural guidelines.

Always provide citations referencing official GCP documentation when presenting architectural advice or product recommendations.
"""

knowledge_assistant = Agent(
    name="knowledge_assistant",
    description="Specialized subagent that queries the Developer Knowledge MCP to retrieve and ground cost optimization recommendations in official GCP architectural guidelines and best practices.",
    model=ConfiguredGemini(
        model=settings.fast_model,
        retry_options=types.HttpRetryOptions(attempts=3),
        use_interactions_api=False,
    ),
    instruction=KNOWLEDGE_ASSISTANT_INSTRUCTION,
    tools=[
        dev_knowledge_mcp_toolset,
    ],
    mode="single_turn",
)
```

### 6. `RootCauseAnalyst` (Spike & Drift Correlation)

- **Model**: `gemini-3.5-flash`.
- **Tools**: `get_precomputed_root_cause`, `get_session_value`, `set_session_value`.
- **Responsibilities**: Investigates spend anomalies by correlating BigQuery resource-level cost spikes with Cloud Asset Inventory (CAI) configuration change history logs (e.g. machine type upgrades or disk size increases).

## Multi-Agent Orchestration Patterns

When designing multi-agent architectures, several standard patterns exist:

1. **Coordinator-Dispatcher**: A central root agent acts as an intelligent router, delegating tasks to dedicated subagents based on intent.
2. **Sequential Pipeline**: Output from Agent A is piped sequentially into Agent B, then Agent C (like an ETL pipeline).
3. **Hierarchical Decomposition**: Complex tasks are recursively broken down by tier-1 coordinators, tier-2 managers, and tier-3 execution workers.
4. **Parallel Collaborative Mesh**: Multiple agents run concurrently on a shared state space, exchanging messages asynchronously.

For _FinSavant_, we selected the **Coordinator-Dispatcher** pattern combined with **Hybrid Model Routing**:

### Why Coordinator-Dispatcher?
- **Domain Isolation**: Financial analytics (BigQuery), operational waste (CAI), and architectural guidance (RAG) require vastly different toolsets and system instructions. Combining them confuses the LLM's tool-selection heuristics.
- **Single-Turn Efficiency**: Most user queries only target one domain (e.g. *"Show my MTD spend"*). The coordinator immediately delegates to `BillingExplorer` and exits, keeping turn latency low.
- **Selective Multi-Agent Audits**: When a user explicitly requests a *"full environment audit"*, the coordinator invokes `BillingExplorer`, `InfrastructureAuditor`, and `CloudAdvisor` sequentially, synthesizing their reports into a unified executive summary.

### Hybrid Model Routing Strategy

To balance inference speed and cost against analytical reasoning depth:
- **Routing & RAG Agents** (`FinOpsCoordinator`, `CloudAdvisor`, `KnowledgeAssistant`): Powered by **`gemini-3.1-flash-lite`**. This slashes orchestration latency and token cost for simple intent classification and RAG lookups.
- **Reasoning & Data Agents** (`BillingExplorer`, `InfrastructureAuditor`, `RootCauseAnalyst`): Powered by **`gemini-3.5-flash`**. This provides high analytical precision for complex SQL generation, data aggregation, and anomaly correlation.

---

## Handling Cross-Cutting Concerns across Agents

Managing multi-agent systems requires handling logging, error resilience, session state, and caching cleanly across all agents without repeating boilerplates.

### 1. Global ADK Plugins (`BasePlugin`)

Instead of duplicating logging or exception handlers inside every subagent constructor, ADK allows registering global plugins on the root `App`:

```python
app = App(
    root_agent=root_agent,
    name="finops_agent",
    context_cache_config=ContextCacheConfig(
        min_tokens=2048,
        ttl_seconds=600,
        cache_intervals=10,
    ),
    plugins=[DefensiveToolErrorPlugin(), FinOpsTelemetryPlugin()],
)
```

- **`DefensiveToolErrorPlugin`**: Globally intercepts unhandled tool exceptions across any subagent, storing formatted error alerts in session state so the coordinator can inform the user gracefully without crashing the process.
- **`FinOpsTelemetryPlugin`**: Automatically instruments OpenTelemetry spans and logs agent handoffs, model execution latency, and token consumption across all turns.

### 2. Overcoming Subagent Event Alignment & `thought_signature` Errors

During multi-agent handoffs in ADK task mode, subagents return their results via `finish_task`. Under certain execution paths, standard event history appending can create an alignment mismatch (a `FunctionResponse` event without a preceding `FunctionCall` event in the coordinator's message history).

Furthermore, Gemini 3.5 API strictly enforces `thought_signature` checks on historical function call events. To solve this cleanly, we created **`clean_history_callback`**:

```python
def clean_history_callback(callback_context: AgentCallbackContext) -> None:
    """Cleans up subagent handoff history by converting subagent FunctionResponses

    in-place into plain-text user messages, avoiding event alignment and thought_signature errors.
    """
    history = callback_context.session.events
    # Scans history and transforms subagent finish_task payloads into plain-text user context
    ...
```

This transforms subagent task responses in-place into clean, plain-text markdown context (`"For context: Subagent BillingExplorer returned: ..."`), wiping internal subagent tool call artifacts and guaranteeing 100% stability across turns! Hurrah!

### 3. Session State, Blackboard Pattern, and In-Memory Caching

Passing massive datasets (e.g. 500 rows of BigQuery billing records) through ADK `SessionState` (`tool_context.state`) creates severe serialization bottlenecks (I/O latency, network payload bloat, and deepcopy CPU spikes). We adopted a two-tier caching strategy:

- **Private In-Memory SQL Cache (`_IN_MEMORY_BQ_CACHE`)**: Raw SQL query results are cached in a thread-safe Python dictionary in process memory, keyed by `session_id`.
- **The Blackboard Pattern**: Shared state keys (`allowed_projects`, `daily_service_costs_30d`, `gcs_secret_waste`) are set in Python memory. Subagents check the blackboard first before triggering new queries, enabling instant data sharing across subagents without LLM JSON re-generation.

---

## Validating Agent Trajectories with `ADK Web`

During local development, validating how the coordinator routes user queries, inspecting tool parameters, and observing subagent handbacks is critical.

We use the ADK CLI web playground to test the multi-agent system interactively:

```bash
make playground
# Or directly via agents-cli:
uv run agents-cli web --agent-dir agent/finops_agent
```

The ADK Web UI launches at `http://localhost:8000`, providing a visual inspector to:
1. Verify that `FinOpsCoordinator` selects the correct subagent based on prompt intent.
2. Inspect raw gRPC tool input arguments and returned output structures.
3. Review system instruction caching and token usage metrics per turn.

---

## Performance Optimisation: Latency, Cost, and Partition Pruning

To keep query execution times under **1.5 seconds** and prevent high BigQuery data scan costs on multi-million row billing export tables, we implemented three core optimisations:

### 1. Partition Pruning (Double-Temporal Filtering)

Standard Google Cloud Billing exports are partitioned by `export_time`. Our BigQuery tool wrapper (`execute_cached_bigquery_sql`) dynamically parses temporal constraints (`export_time`, `usage_start_time`, `usage_end_time`) from the agent's SQL query and pushes them down into the inner scoping subqueries:

```sql
FROM (
  SELECT * FROM `gcp_billing_export_v1_*` 
  WHERE project.id IN (...) 
    AND export_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
    AND usage_start_time >= TIMESTAMP(DATE_SUB(CURRENT_DATE(), INTERVAL 30 DAY))
)
```

This forces BigQuery to prune partitions at table-scan time, shrinking query latency from over 45 seconds to under **800ms**.

### 2. Dynamic Table Routing

Queries that aggregate costs by project or SKU without requesting resource-level fields (like `resource.name` or `resource.global_name`) are automatically rewritten at runtime to target the standard billing table (`gcp_billing_export_v1_*`) rather than the massive resource-level table (`gcp_billing_export_resource_v1_*`). This instantly reduces scanned data volume by **~100x**.

### 3. Deterministic Python Precomputation & Subagent Tool Stripping

Rather than having LLM subagents generate complex SQL queries, inspect raw data rows, and run multi-turn self-correction loops, we implemented native Python precomputation tools (`get_precomputed_spend_analysis` and `get_precomputed_root_cause`):

- **Python Precomputation**: Cost summation, daily spike calculations, MoM changes, and CAI log correlations run natively in Python.
- **Subagent Tool Stripping**: We stripped raw database query tools from `RootCauseAnalyst` and `BillingExplorer`, exposing only the precomputation helpers. This forces them into a single-turn deterministic execution path, reducing prompt token footprint by **90%** and dropping subagent execution time to under **1.5 seconds**!

---

## Test-Driven Development & Unit Testing

To ensure our multi-agent split remains robust against regressions, we built a comprehensive unit test suite in `tests/unit/test_multiagent.py` covering:

- **Router Mocking**: Verifying that `FinOpsCoordinator` correctly delegates cost queries to `BillingExplorer` and zombie queries to `InfrastructureAuditor`.
- **Session State Assertions**: Verifying that subagents write `allowed_projects` and blackboard keys to session memory.
- **Mode & Handback Contracts**: Confirming that `single_turn` subagents (`KnowledgeAssistant`) exit immediately upon execution, and `task` subagents return control cleanly via `finish_task`.
- **Error Recovery**: Asserting that 403 Forbidden errors in `CloudAdvisor` log skipped projects without breaking the execution flow.

Run the test suite from the root directory:

```bash
make test
# Or using pytest directly:
uv run pytest tests/unit/
```

---

## Building the FastAPI Backend-for-Frontend (BFF)

To serve our React SPA workspace while maintaining serverless scalability on Google Cloud Run, we built a thin, high-performance FastAPI Backend-for-Frontend (`bff/fast_api_app.py`).

### 1. Decoupled BFF Architecture
The BFF decouples the React frontend from the AI agent:
- Exposes REST endpoints (`/api/dashboard`, `/api/status`, `/api/feedback`).
- Exposes an SSE endpoint (`/api/chat/stream`) for real-time streaming of agent thought logs, tool execution badges, and A2UI payloads.

### 2. Keep-Alive Heartbeat SSE Streaming
Cloud Run terminates HTTP connections if no bytes are transmitted for a few seconds. To prevent timeouts during multi-tool subagent investigations, the SSE generator emits comment heartbeats every 15 seconds:

```python
# Stream heartbeats every 15 seconds to prevent Cloud Run timeout
seconds_passed = 0
while not task.done():
    await asyncio.sleep(1)
    seconds_passed += 1
    if seconds_passed >= 15:
        # SSE comment heartbeat to keep connection alive
        yield ": heartbeat\n\n"
        seconds_passed = 0
```

### 3. Hybrid Execution Mode (`AGENT_RUNTIME_ID`)
The BFF supports a seamless hybrid execution model:
- **Local Dev Mode (`AGENT_RUNTIME_ID` is unset)**: Loads the ADK agent directly in-process (`from finops_agent.agent import root_agent`) and runs the ADK engine in a background thread using local Application Default Credentials (ADC).
- **Remote Production Mode (`AGENT_RUNTIME_ID` is set)**: Proxies queries to the deployed managed **Gemini Enterprise Agent Runtime** (Vertex AI Reasoning Engine) using the `google-genai` SDK.

### 4. BFF Rate Limiting (`slowapi`)
To prevent Denial of Wallet (DoW) attacks and API quota exhaustion, the BFF applies `slowapi` rate limiting on `/api/chat/stream` and `/api/dashboard`, keyed by the user's authenticated IAP identity (`X-Goog-Authenticated-User-Email`).

---

## Creating & Running the Docker Container

To support both unified local testing and decoupled production deployments, the project provides dedicated Docker configurations:

### 1. Multi-Stage Unified Dockerfile (`Dockerfile`)
Used for local container testing (`make run` / `make docker-build`):
- **Stage 1 (Frontend Builder)**: Uses `node:20-slim` to compile the Vite + React SPA into static production assets (`/dist`).
- **Stage 2 (Python Runtime)**: Uses `python:3.12-slim` with pinned `uv`. Installs virtual environment dependencies via `uv sync --frozen --no-dev`, copies the static frontend assets and `agent/` code, creates a non-root system user (`USER appuser`), and launches `uvicorn`.

### 2. Running Locally with Makefile
Build and run the container locally with zero friction:

```bash
# Build the unified container
make docker-build

# Launch local container with ADC credentials & FinOps environment variables mapped
make run
```

---

## What's Next?

With our multi-agent backend, precomputed toolsets, and FastAPI BFF fully operational and tested, we're ready to build the user interface!

In **Part 4**, we'll dive into **Designing and Building the UI with Google Stitch and A2UI**, exploring how we used Google Stitch to craft our *Emerald Cyber* dark-mode aesthetic and how A2UI dynamically drives interactive SVG area charts, KPI tiles, and waste optimization cards on the React canvas.

Stay tuned!