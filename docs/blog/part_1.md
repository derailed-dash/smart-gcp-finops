# FinSavant Part 1: Building an Agentic FinOps Platform with Google ADK and the Gemini Enterprise Agent Platform - Goals, Architecture, and Tech Stack

## Welcome

Hello folks, Dazbo here. I'm on holiday, which means I've got time to catch up on some blogging of my recent experiments!

![Blogging from Turkey](/docs/images/blogging-in-turkey.jpg)

If you’ve ever had to manage a Google Cloud Platform footprint of any decent size, you’ll know the feeling. You open up the billing console, look at the monthly total, and feel your eyes water. You start digging into dashboards, trying to map raw costs to actual running infrastructure, and quickly realise you’re essentially flying blind.

To be fair, Google has made a bunch of improvements lately, with its own [Google Cloud FinOps Hub](https://docs.cloud.google.com/billing/docs/how-to/finops-hub?utm_campaign=DEVECO_GDEMembers&utm_source=deveco). As Google describes it: 

_"The FinOps hub presents all of your active savings and optimisation opportunities in one dashboard."_

But I wanted to build my own agentic FinOps solution, for a few reasons. Some are about the FinOps capability itself:

- I want to be able to have natural language conversations with the agent. I want to be able to dig into my cost spikes, and ask follow-up questions.
- I want an agentic solution that can combine information like *what* I spent last month, *why* I spent it, and why *spending spikes* occurred.
- I want the solution to be able to immediately spot *orphaned resources*, such as unused VMs, unattached disks, or unused IP addresses. For example, a persistent disk costing us $100 a month might be adding value if it's actually attached to a VM; but it's a total waste of spend if it's not. (Obviously, this is more of a problem for traditional IaaS infrastructure; this is not generally a concern for serverless services.)
- I want the solution to understand Google Cloud *architecture* and *best practices*, so that it can advise *what I should do*, and *why this is the most appropriate course of action*.

But mainly, I wanted an excuse to experiment with some relatively new agentic services in Google Cloud:

- I wanted to deploy to the new Gemini Enterprise [Agent Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime?utm_campaign=DEVECO_GDEMembers&utm_source=deveco); the thing that has replaced Vertex AI Agent Engine.
- I wanted to play with some of the associated [Gemini Enterprise Agent Platform](https://docs.cloud.google.com/gemini-enterprise-agent-platform/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco) capabilities, such as native support for [ADK agents](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk?utm_campaign=DEVECO_GDEMembers&utm_source=deveco), the [Agent Registry](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/agent-registry?utm_campaign=DEVECO_GDEMembers&utm_source=deveco), and built-in [observability and telemetry](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/observability/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco).
- I wanted to experiment with some specific tools and MCP servers.

Specifically:

- Native [BigQuery tools from ADK](https://adk.dev/integrations/bigquery/?utm_campaign=DEVECO_GDEMembers&utm_source=deveco) - in order to interrogate billing information in BigQuery.
- [Google Cloud Assist](https://docs.cloud.google.com/cloud-assist/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco) - to be able to obtain live insights from Google Cloud metrics and logging, and provide recommendations using Google's built-in recommenders.
- The [Asset Inventory API](https://docs.cloud.google.com/asset-inventory/docs/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco) - to determine our exact current deployment configuration, to identify orphaned resources, and to see what has changed.
- The [Developer Knowledge MCP](https://developers.google.com/knowledge/mcp?utm_campaign=DEVECO_GDEMembers&utm_source=deveco) - so that my agent always has the latest knowledge about Google products, services, APIs, architectures, and best practices.

And so, friends, I give you **FinSavant**, an agentic FinOps solution for GCP that gives you an active, infrastructure-aware virtual analyst that combines costs with real-time operational context, and can make recommendations about what you should do next.

This is what it looks like:

![FinSavant](../images/finsavant-explain-spike.png)

I've open sourced the project, and you can find the [project and its code on GitHub](https://github.com/derailed-dash/smart-gcp-finops).

https://github.com/derailed-dash/smart-gcp-finops

## Series Structure

Let's see where we are in this series.

1. Goals, Architecture, and Tech Stack: Capabilities, project goals, target architecture, technology stack, and design decisions. **📍 You are here.**
2. Dev Environment Setup with Google Antigravity, ADK, Agents CLI, MCP & Skills
3. Building the dynamic UI with A2UI
4. Authentication with IAP, Terraform, and CI/CD
5. Observing, Evaluating & Tuning Our Agent with Gemini Enterprise Agent Platform

## FinSavant: How Does It Work?

FinSavant is a conversational agent that:

- Uses **[BigQuery Billing Exports](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)** to know exactly what our costs are, down to the resource ID. Of course, this means you need to be exporting your billing data to BigQuery in the first place. Setting up [billing exports to BigQuery](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery?utm_campaign=DEVECO_GDEMembers&utm_source=deveco) is a standard process.
- Uses **[Google Cloud Asset Inventory](https://docs.cloud.google.com/asset-inventory/docs/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)** to understand our real-time deployment configuration, but also to provide a 35-day audit history of every asset change in our GCP estate.
- Uses **[Google Cloud Assist](https://docs.cloud.google.com/cloud-assist/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)** in order to interrogate our services, metrics and logs, and provide recommendations accordingly.
- Uses **[Developer Knowledge MCP](https://developers.google.com/knowledge/mcp?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)** to ground the agent with both broad and deep Google knowledge. This means that if you ask it any questions relating to Google Cloud, Google APIs, or general Google best practices, the agent will provide factually correct answers that are up-to-date, and with very little hallucination.

By bringing these together under a GenAI agent built with the Google Agent Development Kit (ADK), we have created an assistant that can perform root-cause analysis on cost spikes, as well as provide recommendations on how to fix them.

## Architecture Overview

When designing FinSavant, I wanted a clean separation between the frontend delivery mechanism and the agentic backend, while keeping deployment costs and security overhead to an absolute minimum. 

The overall architecture looks like this:

![FinSavant Solution Architecture](../images/component_architecture.png)

## Tech Stack & Design Decisions

Let’s dive into the core components that make up FinSavant's tech stack and see how they complement one another.

### User Interface: React/Vite

With React I can create a great looking UI, and I have the ability to render dynamic A2UI widgets. (More on this in a future part of the series.) 

_By the way: I'm no frontend developer. I used Stitch to help me design and prototype the frontend UI, and then I used Antigravity (Gemini) to turn this into React code._

I can compile the React UI to clean, static assets, so I don't need Node.js. This means my frontend container image will be pretty small, and therefore fast and cheap to run.

### Rich UI with Agent-to-UI (A2UI)

Rather than building a static dashboard or a free-form chatbot, FinSavant uses **Agent-to-UI (A2UI)** to dynamically render rich UI components like tables, charts, and summary cards directly from the LLM. This ensures the interface is always context-aware and adapts to the user's specific query. 

A2UI is Google's declarative specification that enables agents to generate dynamic user interfaces in the form of JSON objects. So for FinSavant, the agent builds the UI component on-the-fly, and then our frontend just converts this JSON object into a React component and renders it.

This is a game-changer for building a UI. I don't have to hard-code any UI components - the agent decides what to display in real time! I'll show you exactly how to do this in a future part of the series.

### Backend-for-Frontend (BFF)

The FastAPI BFF simply acts as a secure proxy. It streams queries to the agent and receives structured responses. But also, it allows us to decouple the backend from the UI. If I want to surface this application through a different UI in the future - like [Gemini Enterprise](https://docs.cloud.google.com/gemini/enterprise/docs) - I can.

### UI & BFF Unified Container

I've packaged the React frontend and FastAPI BFF into a single container image. This eliminates cross-origin resource sharing (CORS) headaches, minimises the runtime footprint, and simplifies the deployment.

### Cloud Run for Container Hosting

[Cloud Run](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run?utm_campaign=DEVECO_GDEMembers&utm_source=deveco) is Google's serverless, zero-ops, autoscaling container hosting environment. This is perfect for hosting our UI/BFF container. There are a number of useful features I'm going to make use of:

- It scales to 0, so it doesn't cost anything when there's no traffic.
- It autoscales based on demand, but we can limit the number of instances in order to control costs.
- It natively integrates with Google Identity-Aware Proxy, providing a trivial way to ensure only authenticated / authorised users can get to our application. (This native integration, without the need for a load balancer, is a fairly new feature.)
- We can map a domain name to our Cloud Run service, without the need for a separate load balancer. (This is quite a new feature.)

### Authentication with Identity-Aware Proxy

I've secured the Cloud Run service using Google's [Identity-Aware Proxy (IAP)](https://docs.cloud.google.com/iap/docs/concepts-overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco). This is a cool service that both authenticates and authorises users before they can access our Cloud Run service. Unauthorised users will not be able to see the application.

Until recently, the only way to use IAP with Cloud Run was to put a load balancer in front of the Cloud Run service and associate IAP with the LB. This adds additional complexity and cost. 

But now we can secure a Cloud Run service directly with IAP, without needing the LB. I've [blogged about this](https://medium.com/google-cloud/using-google-identity-aware-proxy-iap-with-cloud-run-without-a-load-balancer-27db89b9ed49?sharedUserId=derailed.dash) before, when the feature first went into _Preview_. But now it's [_Generally Available_](https://cloud.google.com/blog/products/serverless/iap-integration-with-cloud-run?utm_campaign=DEVECO_GDEMembers&utm_source=deveco).

![Cloud Run IAP](../images/cloudrun_iap.png)

### Agent Orchestration: Google Agent Development Kit (ADK)

ADK is an open source framework and SDK for building agents and agentic systems. These days I reach for it automatically.

This is what it gives us:

- Powerful multi-agent orchestration.
- Session context management.
- Bi-directional streaming support.
- Model-agnostic.
- Hosting-agnostic, but optimised for hosting on the Google Agent Runtime.
- Integrates natively with Gemini Enterprise Agent Platform / Agent Runtime.
- Easy to configure telemetry and observability.
- Really useful local development user interfaces.

### Agent Runtime for ADK Agent Hosting

Having decided I wanted to deploy the agent itself independently of the frontend and FastAPI, the next question is: where should we deploy the agent itself?

In days gone by I would probably have deployed it to a separate Cloud Run service. But now we have [Agent Runtime](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime), Google's evolution of their previous product, Agent Engine. It is built for hosting agents and has a number of benefits:

- It is trivial to deploy ADK agents to Agent Runtime, using the [Agents CLI](https://google.github.io/agents-cli/?utm_campaign=DEVECO_GDEMembers&utm_source=deveco).
- It is serverless and autoscaling.
- When there's no demand for the agent, there's no cost.
- Exposing the agent's endpoint to consumers (like our BFF in Cloud Run) is trivial.
- Agents deployed to Agent Runtime are automatically registered in the Gemini Enterprise Agent Platform's [Agent Registry](https://docs.cloud.google.com/agent-registry/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco).
- Agents deployed to Agent Runtime can leverage the various capabilities of [GEAP](https://docs.cloud.google.com/gemini-enterprise-agent-platform/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco), like [Memory Bank](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank?utm_campaign=DEVECO_GDEMembers&utm_source=deveco), [Agent Gateway](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco), [Model Armor](https://docs.cloud.google.com/model-armor/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco), [telemetry](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/observability/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco), and [agent evaluations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/agent-evaluation?utm_campaign=DEVECO_GDEMembers&utm_source=deveco).

![Gemini Enterprise Agent Platform Overview](../images/geap.png)

### Hybrid Execution Mode

To support a fast local development cycle, the BFF supports two different run modes:

*   **Remote Execution Mode**: In staging and production, the BFF acts as a stateless proxy to the remote agent, running on the Google Agent Runtime.
*   **Local Fallback Mode**: If no remote agent runtime ID is configured, FastAPI loads the agent code directly into the container and runs the ADK engine locally in a background thread, using the developer’s Application Default Credentials (ADC).

### Project and Organisational Scope

I want FinSavant to give me a holistic view across all the projects that are incurring cost against my billing account. But at the same time, I only want FinSavant to provide insights for projects that I actually have authority to see.

But GCP resource hierarchies are rarely neat and tidy. Some of my projects live inside a nice, clean Google Cloud organisation, and some are _standalone_ - essentially orphaned projects floating in the ether that are linked to the billing account but don't inherit anything from an organisation root.

![GCP Resource Hierarchy & Billing Relationships](../images/resource_hierarchy.png)

To solve this, I designed a multi-layered discovery and security boundary:

1. **Billing-Led Discovery**: 
   Rather than scanning the Resource Manager from the top down (which misses standalone projects entirely), the backend starts by querying the Cloud Billing API to retrieve every project linked to our central billing account. This gives us a comprehensive list of all projects incurring costs.

2. **Hierarchical Permission Resolution (With Caching)**:
   Once we have the master list of billing projects, we need to know what the user is actually allowed to see. The discovery service attempts a top-down interrogation:
   - **Org-Level Scan (Fast)**: If a target organisation ID is configured, the backend queries Cloud Asset Inventory's IAM policies. This is extremely fast because it lets us resolve all of the user's project bindings across the entire hierarchy in a single API call.
   - **Project-Level Fallback (Granular)**: If organisation-wide access isn't available or fails (as is often the case with standalone projects outside the org boundary), the service seamlessly falls back to a project-by-project scan, calling `getIamPolicy` on each individual project in the billing list to compile the user's allowed set.
   - **Performance Protection**: To prevent rate limits and quota exhaustion from repeating project-by-project IAM scans, this resolved set is cached in-memory with a thread-safe, 10-minute time-to-live (TTL).

3. **IAP-Enforced Row-Level Security**:
   We serve the React dashboard and agent chat through an Identity-Aware Proxy (IAP). When a user requests data, the BFF extracts their email from the `x-goog-authenticated-user-email` header. It resolves their allowed projects list and sets it in a local context variable.
   
   To prevent prompt injections or the agent from hallucinating data about projects the user shouldn't see, we intercept all BigQuery billing queries and wrap them in a subquery that filters based on only the allowed projects. This means that even if the agent is querying the whole dataset, the database engine itself enforces strict row-level filtering based on the logged-in user's identity. If the user only has access to one project, that's all the agent can query.

### Cloud Asset Inventory (CAI)

I'm using CAI for:
*   **Zombie Detection**: I built custom CAI queries to instantly scan for unattached disks and idle external IPs.
*   **Detective Mode**: When we detect a cost spike, the agent uses CAI history to audit the exact configuration changes that occurred on that resource over the last 35 days. For example, detecting that an engineer upscaled a Cloud Run instance memory limit.

### BigQuery Tool Calls From Our Agents

I want to be able to query my billing data - stored in BigQuery - using natural language prompts. I'm achieving this in two different ways, depending on where I'm going from.

- In my development workspace, I'm using Google's remotely managed BigQuery MCP server (`https://bigquery.googleapis.com/mcp`).
- In our FinSavant ADK agent itself, I'm using ADK's native `BigQueryToolset` directly. In doing so, we simplify authentication, reduce runtime latency when making BQ calls, reduce dependency on an external service, and align with ADK best practices. 

### Developer Knowledge MCP

To make FinSavant's advice more than just generic feedback, we need to ground its recommendations in official Google Cloud engineering standards. That's where the **Developer Knowledge MCP** comes in.

This MCP server provides a direct gateway to Google's official developer documentation, product guides, API reference material, and the Cloud Architecture Framework. Instead of relying on the LLM's static training data, the agent can query this knowledge base in real time to retrieve authoritative, up-to-date information.

In FinSavant, we use the Developer Knowledge MCP to:
*   **Determine the Best Course of Action**: When the agent discovers a cost anomaly, it doesn't just throw alerts. It queries the MCP to formulate an appropriate, structured response grounded in official documentation.
*   **Verify Architectural Best Practices**: It checks current Google Cloud design patterns, ensuring the agent doesn't recommend legacy or non-optimal resource structures.
*   **Provide Actionable Remediation**: If an idle persistent disk is flagged, the agent uses the MCP to outline the exact recommended steps to snapshot and clean up the asset safely, linking the user directly to the relevant documentation.
*   **Eliminate Hallucinations**: By grounding the agent in real-time documentation, we ensure any CLI commands or configuration snippets it presents are correct and match the latest GCP standards.

## Let's See It In Action!

In this short video I demonstrate a number of FinSavant features, including:

- Using starter chips to kick off an initial conversation, e.g. looking for cost spikes over the last 30 days
- Seeing the various tools and MCP servers called in real time
- Seeing recommendations based on the findings
- Watching tiles and graph widgets being created in real time using A2UI
- Asking follow-up questions about particular projects
- Looking for other cost anomalies

[![My Google FinOps AI Agent using ADK, BQ, Cloud Asset Inventory, and Google Developer Knowledge MCP](https://img.youtube.com/vi/zs_IRUxIx4E/maxresdefault.jpg)](https://youtu.be/zs_IRUxIx4E)

## What’s Next?

In the next part of this series, we'll get our hands dirty and look at **Part 2: Building the Agentic Solution**.

Stay tuned!

## Useful Links and References

### Project Demo & Portfolio

- [Dazbo's Portfolio](https://dazbo.co.uk)
- [FinSavant YouTube Demo](https://youtu.be/zs_IRUxIx4E)

### Gemini Enterprise Agent Platform & ADK

- [Gemini Enterprise Agent Platform Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Agent Runtime (ADK Hosting)](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/runtime?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [ADK Agent Building Guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Agents CLI Documentation](https://google.github.io/agents-cli/?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [ADK BigQuery Tool Integration](https://adk.dev/integrations/bigquery/?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Agent Registry Overview](https://docs.cloud.google.com/agent-registry/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [GEAP Memory Bank](https://docs.cloud.google.com/gemini-enterprise-agent-platform/scale/memory-bank?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Agent Gateway Documentation](https://docs.cloud.google.com/gemini-enterprise-agent-platform/govern/gateways/agent-gateway-overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Model Armor Security Overview](https://docs.cloud.google.com/model-armor/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [GEAP Observability & Telemetry](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/observability/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Agent Evaluations](https://docs.cloud.google.com/gemini-enterprise-agent-platform/optimize/evaluation/agent-evaluation?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)

### Google Cloud Services & APIs
- [Cloud Run Overview](https://docs.cloud.google.com/run/docs/overview/what-is-cloud-run?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Identity-Aware Proxy (IAP) Overview](https://docs.cloud.google.com/iap/docs/concepts-overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Google Cloud Assist](https://docs.cloud.google.com/cloud-assist/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Cloud Asset Inventory (CAI) API](https://docs.cloud.google.com/asset-inventory/docs/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Developer Knowledge MCP Server](https://developers.google.com/knowledge/mcp?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)

### GCP Billing & FinOps
- [Google Cloud FinOps Hub](https://docs.cloud.google.com/billing/docs/how-to/finops-hub?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [BigQuery Billing Exports Setup](https://docs.cloud.google.com/billing/docs/how-to/export-data-bigquery?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)

### Articles & Resources
- [Using Google IAP with Cloud Run without a Load Balancer (Dazbo on Medium)](https://medium.com/google-cloud/using-google-identity-aware-proxy-iap-with-cloud-run-without-a-load-balancer-27db89b9ed49?sharedUserId=derailed.dash)
- [Cloud Run IAP Integration Announcement](https://cloud.google.com/blog/products/serverless/iap-integration-with-cloud-run?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)

