# FinSavant: Authentication & Cost Model

This document explains how **FinSavant** manages authentication (API Keys vs. Google Cloud Vertex AI) across development and production environments, and details the primary cost drivers associated with running the application.

---

## 1. Authentication Architecture: API Keys vs. Vertex AI

FinSavant supports two authentication modes for generative AI inferences, governed by the `GOOGLE_GENAI_USE_VERTEXAI` environment variable configured in [agent/finops_agent/config.py](file:///home/darren/localdev/smart-gcp-finops/agent/finops_agent/config.py#L50-L55).

### Default Mode: Vertex AI & Google Cloud IAM (Dev & Production)

By default, `GOOGLE_GENAI_USE_VERTEXAI=True`. In this mode:
* **No `GEMINI_API_KEY` is required or used.**
* The underlying `google-genai` SDK initializes the client with `vertexai=True` (see [agent/finops_agent/client.py](file:///home/darren/localdev/smart-gcp-finops/agent/finops_agent/client.py#L39-L43)), routing all model calls through **Vertex AI / Gemini Enterprise Agent Platform**.
* **Local Development**: Authenticates using your local **Application Default Credentials (ADC)** generated via `gcloud auth application-default login`.
* **Deployed Cloud Environments (Cloud Run / Agent Runtime)**: Authenticates using the attached **Google Cloud Service Account** identity and IAM role bindings (`roles/aiplatform.user`, `roles/bigquery.jobUser`, `roles/cloudasset.viewer`).

### Optional Local Dev Mode: Google AI Studio (`GEMINI_API_KEY`)

Developers can optionally switch model inferences to Google AI Studio by setting `GOOGLE_GENAI_USE_VERTEXAI=False` in `.env`:
* In this mode, the application loads `GEMINI_API_KEY` from environment settings and passes it to the `google-genai` client SDK.
* All Gemini model calls (`gemini-3.6-flash` and `gemini-3.5-flash-lite`) are routed to Google AI Studio (`generativelanguage.googleapis.com`).

> [!IMPORTANT]
> **Google Cloud ADC is Always Required**: Even if `GEMINI_API_KEY` is used for LLM inference, FinSavant still requires valid Google Cloud IAM credentials (ADC) to execute BigQuery billing export queries and perform Cloud Asset Inventory (CAI) resource sweeps.

---

## 2. FinSavant Cost Drivers & Optimisations

Running FinSavant incurs costs across four main categories:

```
                              ┌─────────────────────────────────────────┐
                              │           FinSavant Cost Drivers        │
                              └────────────────────┬────────────────────┘
                                                   │
         ┌──────────────────────┬──────────────────┴───────────────────┬──────────────────────┐
         ▼                      ▼                                      ▼                      ▼
┌─────────────────┐    ┌─────────────────┐                   ┌──────────────────┐   ┌───────────────────┐
│ 1. LLM / GenAI  │    │  2. BigQuery    │                   │ 3. Infrastructure│   │ 4. Asset Scans    │
│    (Vertex AI)  │    │  Billing Data   │                   │    (Cloud Run    │   │   (Cloud Asset    │
│ Gemini 3.6 & 3.5│    │ Scanned Bytes   │                   │ & Agent Runtime) │   │    Inventory)     │
└─────────────────┘    └─────────────────┘                   └──────────────────┘   └───────────────────┘
```

### 1. Generative AI / Model Inference Costs (Vertex AI)

* **Models In Use**:
  * `gemini-3.6-flash`: Main reasoning orchestrator and analytical subagents (`BillingExplorer`, `InfrastructureAuditor`, `RootCauseAnalyst`).
  * `gemini-3.5-flash-lite`: Fast model for lightweight subagents (`CloudAdvisor`, `KnowledgeAssistant`) and semantic caching.
* **Billing Location**: Charged directly to the Google Cloud Billing Account attached to `GOOGLE_CLOUD_PROJECT` under Vertex AI pricing (per 1M input/output tokens and context cache storage).
* **Built-in Cost Optimisations**:
  * **Context Caching**: Caches system instructions and heavy tool declarations model-side to slash token consumption on multi-turn conversations.
  * **Semantic Caching**: Skips LLM calls for semantically matching prompts using `gemini-3.5-flash-lite`.
  * **Python Precomputation**: Executes heavy data aggregations natively in Python (`get_precomputed_spend_analysis`), reducing LLM reasoning loop turns and token generation.

### 2. BigQuery Billing Export Query Costs

* **Source**: The agent queries Google Cloud billing export datasets (`gcp_billing_export_v1_*` and `gcp_billing_export_resource_v1_*`) to analyse spend trends and SKU-level anomalies.
* **Billing Location**: Standard BigQuery on-demand analysis pricing ($6.25 per TB scanned, unless flat-rate/editions capacity is enabled).
* **Built-in Cost Optimisations**:
  * **Partition Pruning**: Mandatory temporal filtering on `export_time` drops scanned data footprint by over 90%.
  * **Dynamic Table Routing**: Automatically redirects queries that do not reference resource dimensions away from the massive resource export table to the 100x smaller standard billing table.
  * **In-Memory Caching**: Caches BigQuery SQL query results in Python memory (`_IN_MEMORY_BQ_CACHE`) to avoid duplicate scans.

### 3. Infrastructure & Hosting Costs (Deployed Environments)

When deployed to Google Cloud via Terraform ([deployment/README.md](file:///home/darren/localdev/smart-gcp-finops/deployment/README.md)):
* **Google Cloud Run**: Hosts the FastAPI Backend-for-Frontend (BFF) and compiled React static assets. Billed for CPU/Memory allocation during active request processing (scales to zero when idle).
* **Gemini Enterprise Agent Runtime**: Hosts the standalone ADK Agent runtime executing cognitive loops and tool invocations. Billed as serverless compute.
* **Identity-Aware Proxy (IAP) & Networking**: IAP identity verification is free of charge; standard Cloud Run ingress/egress data processing fees apply.

### 4. Cloud Asset Inventory (CAI) & External APIs

* **Zombie Asset Sweeps**: Scans organization/project resources for unattached disks and idle IP addresses. API usage is typically within standard GCP free tier limits or incurs negligible API call costs.
* **Developer Knowledge MCP**: Public Google Developer Knowledge API for best-practice grounding (fully managed by Google at zero additional infrastructure cost).

---

## 3. Quick Reference Matrix

| Feature | Local Development (Default) | Local Development (AI Studio) | Production / Staging Deployment |
| :--- | :--- | :--- | :--- |
| **`GOOGLE_GENAI_USE_VERTEXAI`** | `True` | `False` | `True` |
| **`GEMINI_API_KEY` Required?** | No | Yes | No |
| **GenAI Credential** | Developer ADC (`gcloud auth`) | `GEMINI_API_KEY` string | Service Account IAM Role |
| **LLM Billing Location** | GCP Project Billing Account | AI Studio Account | GCP Project Billing Account |
| **BigQuery Credential** | Developer ADC (`gcloud auth`) | Developer ADC (`gcloud auth`) | Service Account IAM Role |
| **BigQuery Billing Location** | GCP Project Billing Account | GCP Project Billing Account | GCP Project Billing Account |
