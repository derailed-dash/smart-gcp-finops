# Product Specification: FinSavant

**FinSavant** is a serverless, agentic FinOps solution for Google Cloud Platform (GCP) designed to help organisations understand, manage, and optimise their cloud infrastructure spend.

---

## 1. Product Goals

*   **Orchestration**: Leverage the Google Agent Development Kit (ADK) to build a robust multi-agent cognitive loop.
*   **Billing Auditing**: Query and aggregate billing datasets hosted in BigQuery (GCP Standard and Resource-level billing exports).
*   **Infrastructure Auditing**: Integrate with Google Cloud Asset Inventory (CAI) to audit live resource states and track configuration history.
*   **Active Optimisation**: Invoke Gemini Cloud Assist to query GCP recommender recommendations and active system logs.
*   **Grounding**: Reference Developer Knowledge base to ground rightsizing and architecture optimization advice in official GCP best practices.
*   **User Interface**: Provide an interactive React dashboard combining natural language chat with rich, structured visual canvas elements (A2UI).

---

## 2. Target Audience

1.  **FinOps Practitioners**: Need comprehensive, multi-project aggregations, cost spike tracking, and savings forecasts.
2.  **Cloud Administrators / DevOps Engineers**: Need to inspect active configurations, locate unattached/idle zombie resources, and review rightsizing recommendations.
3.  **Financial Managers**: Need high-level month-to-date metrics, forecasts, and savings breakdowns.

---

## 3. Core Functional Requirements

### 3.1 Spend Exploration & Forecasting
*   **Standard Billing Analysis**: Query service, SKU, and project costs over temporal bounds.
*   **Resource-level Analysis**: Trace specific individual resource costs by name (using the resource-level billing export).
*   **MTD & Forecast Curves**: Generate Month-to-Date spend metrics and project end-of-month spend using linear regression or seasonality forecasting.

### 3.2 Active Infrastructure Optimization
*   **Zombie Asset Detection**: Identify waste including unattached persistent disks and idle static IP addresses.
*   **Live Rightsizing Recommendations**: Fetch real-time VM machine type and disk performance recommendations directly via Gemini Cloud Assist.

### 3.3 Root Cause Analysis (Spike Investigation)
*   Compare a cost spike date with previous baseline days using resource-level tables to isolate high-cost-growth resource URIs.
*   Scan CAI configuration drift history logs around the spike timeframe to correlate cost increases with resource creation or size modification events.

### 3.4 Best Practice Alignment
*   Ground recommendation summaries in official GCP documentation (e.g. storage tiers, VM scheduling, committed use discounts) via Developer Knowledge MCP.
*   Scope recommendations to only match active deployed service footprints.

---

## 4. User Experience & Interface (A2UI)

The UI utilizes the **Agent-to-UI (A2UI)** protocol to render structured widgets returned from the agent:
*   **`explorer` Component**: Interactive cost tables breaking down project and service drivers.
*   **`dashboard` Component**: Renders Month-to-Date curves and cost timeline charts.
*   **`recommendations` Component**: Shows individual optimization suggestions with cost impact and a target "Apply" workflow.

---

## 5. Deployment & Telemetry

*   **Hosting**: Decoupled architecture with the UI/BFF hosted on Google Cloud Run (secured by Identity-Aware Proxy) and the cognitive loop hosted in **Gemini Enterprise Agent Runtime**.
*   **Telemetry**: Instrument OpenTelemetry tracing on all LLM calls, tool execution callbacks, and agent-to-agent delegation handoffs.
