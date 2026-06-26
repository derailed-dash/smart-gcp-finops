# FinSavant Part 1: Overall Series Goals & Design

Hello folks, Dazbo here.

If you’ve ever had to manage a Google Cloud Platform footprint of any decent size, you’ll know the feeling. You open up the billing console, look at the monthly total, and feel your eyes water. You start digging into static dashboards, trying to map raw costs to actual running infrastructure, and quickly realise you’re essentially flying blind.

Standard dashboards are great at telling you *what* you spent last month. But they are completely useless at telling you *why* you spent it, *if* you actually needed to spend it, or *which* engineer left an unattached 2TB SSD running in a staging project three months ago. 

This is the genesis of **FinSavant**—an agentic FinOps solution for GCP. My goal was to move past passive cost reporting and build an active, infrastructure-aware virtual analyst that combines financial truth with real-time operational context.

In this first part of our series, I'll walk you through the design principles, the target architecture, and the tech stack integrations that power FinSavant.

---

## The Vision: Financial Truth meets Operational Context

A standard FinOps dashboard operates in a silo. It pulls from the BigQuery billing export, aggregates the numbers, and plots them on a pretty chart. But financial data lacks **operational reality**. 

For example, a persistent disk that costs £100 a month looks exactly the same in a billing report whether it is attached to your core database or sitting completely idle. To find out if it's waste, an analyst has to manually check Compute Engine, check the attachment status, and track down the owner. 

FinSavant solves this by combining three elements:
1. **Financial Truth (BigQuery Billing Exports)**: Knowing exactly what is being spent down to the resource ID.
2. **Operational Reality (Cloud Asset Inventory)**: Understanding the real-time configuration state and 35-day audit history of every asset in your GCP estate.
3. **GCP Best Practices (Developer Knowledge MCP)**: Grounding the agent's insights in official Google Cloud architecture guidelines.

By bringing these together under a GenAI agent built with the Google Agent Development Kit (ADK), we have created an assistant that can perform root-cause analysis (RCA) on cost spikes entirely on its own.

---

## The Architecture: High-Performance Canvas & Remote Brains

When designing FinSavant, we wanted a clean separation between the frontend delivery mechanism and the reasoning backend, while keeping deployment costs and security overhead to an absolute minimum. 

In production, the architecture splits into two main environments:
*   **The Client & BFF (Cloud Run)**: We use the **Unified Container** pattern to package a React frontend and a FastAPI Backend-for-Frontend (BFF) into a single Cloud Run image. This eliminates cross-origin resource sharing (CORS) headaches, minimises our runtime footprint, and simplifies authentication.
*   **The Reasoning Loop (Gemini Enterprise Agent Platform)**: The actual ADK agent logic is deployed to the **Gemini Enterprise Agent Platform (GEAP) Agent Runtime** (formerly Vertex AI Agent Engine or Reasoning Engine). The FastAPI BFF simply acts as a secure proxy, streaming queries to GEAP and receiving structured responses.

Here is how the request flow works in practice:

![FinSavant Solution Architecture](../images/part1_architecture.png)

### Hybrid Execution Mode
To support a fast local development cycle, the BFF supports a **hybrid execution architecture**:
*   **Local Fallback Mode**: If no remote agent runtime ID is configured, FastAPI loads the agent code directly into the container and runs the ADK engine locally in a background thread, using the developer’s Application Default Credentials (ADC).
*   **Remote Execution Mode**: In staging and production, the BFF bypasses local execution and acts as a stateless proxy to the remote GEAP Agent Runtime.

---

## Showcasing the Gemini Enterprise Agent Platform (GEAP)

Deploying a production-grade agent requires more than just running a Python loop. You need governance, security, and observability. This is why we chose the **Gemini Enterprise Agent Platform (GEAP)** as our runtime environment. 

By running on the GEAP Agent Runtime, FinSavant gains several critical advantages:

*   **Native ADK Integration**: GEAP is built from the ground up to support the Google Agent Development Kit, allowing us to package complex multi-agent flows and custom tools without having to write custom container management layers.
*   **Agent Registry**: When deployed, the agent is automatically registered in the centralised Google Cloud Console **Agent Registry** catalog under a unique URN namespace. This provides the operations team with a single pane of glass to audit, version, and manage all deployed agents across the organisation.
*   **Observability and Telemetry**: We get native tracing of agent trajectories. We can inspect exactly what reasoning path the model took, which tools it invoked, and what payloads were returned, making debugging agent loops significantly easier.
*   **Model Armor & Agent Gateway**: Security is paramount when an agent has read access to your billing data. GEAP’s **Agent Gateway** routes and monitors traffic, working alongside **Model Armor** to apply content security filters, block prompt injection attacks, and prevent unauthorised data exfiltration.

---

## Core Tech Stack & Decisive Integrations

Let’s dive into the core components that make up FinSavant's toolset and how they complement one another.

### 1. Google Agent Development Kit (ADK)
The ADK is the orchestrator. It manages session context, wraps our custom tools, and handles the conversation loops with the model. Crucially, we leverage ADK's **Context Caching** features to cache system instructions and tool definitions model-side, which slashes token usage and drops latency.

### 2. Cloud Asset Inventory (CAI)
Instead of querying individual GCP APIs (which is slow and rate-limited), we use CAI's `searchAllResources` and `batchGetAssetsHistory` endpoints. 
*   **Zombie Detection**: We built custom CAI queries to instantly scan for unattached disks (`state=READY AND -users:*`) and idle external IPs.
*   **Detective Mode**: When BigQuery highlights a cost spike, the agent uses CAI history to audit the exact configuration changes that occurred on that resource over the last 35 days (e.g., detecting that an engineer upscaled a Cloud Run instance memory limit).

### 3. Developer Knowledge MCP
We connected the agent to the remote Developer Knowledge MCP server. When the agent detects an inefficiency, it doesn't just say "delete this"; it queries the MCP to find official Google Cloud guidance on cost-optimisation strategies to back up its recommendation.

### 4. BigQuery Remote MCP
To query our billing data, we integrated the remote BigQuery MCP server (`https://bigquery.googleapis.com/mcp`). Because it is a remote, fully managed Google endpoint, we don't need to deploy or manage any local MCP server containers. The agent connects to it via authenticated OAuth 2.0 headers.

#### Deep Dive: BigQuery MCP vs. Direct ADK Toolsets vs. Direct BQ Client Libraries

When connecting an agent to BigQuery, we had to weigh the architectural trade-offs of different integration patterns:

| Feature | BigQuery MCP (Remote) | BigQueryToolset (ADK) | Direct BQ Client Library / Custom Tools |
| :--- | :--- | :--- | :--- |
| **Complexity** | **Medium**: Requires configuring connection parameters and Oauth 2.0 header providers. | **Low**: Fastest setup within the ADK ecosystem. | **Medium to High**: High development overhead; must write custom connection, querying, and parsing logic. |
| **Portability** | **High**: Cross-compatible with any MCP-compliant client. | **Medium**: Restricted to the ADK framework. | **Universal**: Can be used in any Python script or framework. |
| **State** | **Stateful**: Persistent session connections. | **Stateless**: Simple API-level calls. | **Stateless**: Managed entirely by your application logic. |
| **Streaming** | **No**: Tool execution is blocking. | **No**: Blocking. | **Yes**: Allows streaming of data chunks for lower latency UX. |
| **Governance** | Lacks business glossary (relies on schema inference). | Lacks business glossary (relies on schema inference). | Customised; can wrap query validation and access controls. |

**Why we chose a hybrid approach**:
For general database discovery (listing datasets, verifying table schemas), we let the agent use the **BigQuery Remote MCP**. It provides a standardized, robust interface that the LLM is already familiar with.

However, for execution, relying solely on raw MCP query tools carries performance and security risks. To mitigate this:
1.  **Security**: We applied a custom tool filter to exclude raw remote query execution tools, protecting the database from arbitrary SQL write actions.
2.  **Performance & Caching**: We created a custom ADK tool called `execute_cached_bigquery_sql`. When the agent wants to run a query, it routes it through this custom tool, which applies a thread-safe, 5-minute TTL cache. This bypasses the blocking nature of the MCP for duplicate queries (like fetching daily spend trends) and significantly accelerates the React canvas updates.

---

## High-Level Design Decisions (ADR Highlights)

While we will cover the deployment and infrastructure details in a later post, it’s worth highlighting how we laid the groundwork for a secure, low-cost enterprise footprint:

*   **Native Cloud Run IAP**: We secured our Cloud Run app using Identity-Aware Proxy (IAP) directly at the service level using the `google-beta` Terraform provider. This allowed us to avoid the high cost of a Global Application Load Balancer (ALB), keeping our monthly infrastructure spend to pennies.
*   **Decoupled Staging & Prod CI/CD**: We split our GitHub Actions pipelines so that staging deployments trigger automatically, while production deployments require a manual release trigger (the "Manual Gate" pattern).
*   **GCS Remote State**: All infrastructure is managed declaratively via Terraform, utilizing a GCS bucket with state locking to prevent deployment conflicts.

---

## What’s Next?

With the goals, architecture, and technology integrations defined, we had our blueprint. In the next part of this series, we will get our hands dirty and look at **Part 2: Building the Agentic Solution**, detailing how we bootstrapped the project with the Agents CLI, handled credential refreshing for long-running agent threads, and implemented the custom ADK callbacks.

Stay tuned, and hurrah for lower cloud bills!
