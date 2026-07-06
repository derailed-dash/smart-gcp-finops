# FinSavant Part 2: Building an Agentic FinOps Platform - Development Environment Setup, Google Antigravity, MCPs and Skills, and ADK Bootstrapping with Agents CLI

## Welcome to Part 2

Welcome back, friends!

In the [previous part](todo link) I described the purpose of [FinSavant](todo_link), the motivation for creating it, its overall architecture and tech stack, and how it works.

In this part we're going to use FinSavant as a case study in how to setup a development environment for the purposes of building such an ADK-based agentic solution. We'll cover:

1. Using Antigravity IDE
1. Overall project workspace structure
1. Setting up agent skills for your coding agent
1. My project's `GEMINI.md` (or if you prefer, `AGENTS.md`)
1. My documentation approach
1. Setting up MCP servers for your coding agent, such as BigQuery MCP
1. Scaffolding the intial ADK agent using Google Agents CLI and its supporting skill
1. Getting started with a Makefile

Sound good? Let's get cracking!

## Series Orientation

Let's see where we are in this series.

1. Goals, Architecture, and Tech Stack: Capabilities, project goals, target architecture, technology stack, and design decisions.
2. Development Environment Setup, Google Antigravity, MCPs and Skills, and ADK Bootstrapping with Agents CLI **📍 You are here.**
3. Buliding the ADK Agent and API
4. Designing and Building the UI with Google Stitch and A2UI
5. Deployment with Gemini Enterprise Agent Platform, Agent Runtime, Cloud Run and IAP
6. Automating Deployment with CI/CD and Terraform
7. Agent Observability, Evaluation, and Tuning with Gemini Enterprise Agent Platform

## Getting Started with Antigravity IDE

These days, my favourite coding environment _for any significant project_ is Antigravity IDE. This is Google's agentic integrated development environment. 

TODO: Agy overview and download link

(By the way, I often refer to Antegravity as _Agy_.)

## Project Structure

Here's the rough outline of the project structure we'll be creating. We won't be building all of this structure here; nor does this represent the final state of the project.  But it gives you an idea of where we're heading. (I'll explain the `*` in a minute!)

```text
  smart-gcp-finops/
* ├── app/                # ADK agent package
  │   ├── finops_agent/       # Root agent
  │   ├── .env                # Agent specific environment vars
  │   ├── Dockerfile          # For deploying agent to Agent Runtime
  │   └── pyproject.toml      # Agent runtime dependencies
* ├── bff/                # Backend-for-Frontend (API)
* ├── deployment/         # Infrastructure & CI/CD (Terraform IaC)
* │   ├── terraform/          # Centralised IaC for Prod & Staging
  │   └── README.md           # Deployment documentation
* ├── docs/               # Project documentation
* │   ├── images/             # Diagrams and architectural visual assets
  │   ├── DESIGN.md           # Visual identity, components, and UI design
  │   ├── PRD.md              # Product specification
  │   ├── architecture-and-walkthrough.md # Solution blueprints, ADRs, and component data flows
  │   └── testing.md          # Testing strategy and verification instructions
* ├── frontend/           # React UI frontend
* ├── notebooks/          # Jupyter notebooks for prototyping and evaluation
* ├── scripts/            # Environment setup and other utility scripts
  │   └── setup-env.sh        # Configure local environment including Google auth / ADC
* ├── tests/              # Unit and integration test suites
* │   ├── eval/               # Agent evaluation
* │   ├── unit/               # Unit tests
* │   └── integration/        # Integration tests
* ├── .gemini/            # Workspace Gemini configuration
  │   └── settings.json       # E.g. MCP servers
* ├── .github/            # GitHub Actions workflows and CI/CD
* ├── .env                # Root environment vars (dev setup, unified container, GitHub, etc)
  ├── .envrc              # Automatically launch when entering this directory
* ├── .gitignore          # Exclude from git
* ├── Makefile            # Centralised developer convenience commands
* ├── GEMINI.md           # Development agent context & guidelines
* ├── LICENSE             # Standard open-source license file
* ├── pyproject.toml      # Root project configuration / dependencies
* ├── README.md           # Developer documentation homepage
  └── TODO.md             # TODO list
```

If you wanted to build such a structure from scratch, here's a cool thing to try...

1. Create your new project folder, e.g. `smart-gcp-finops`
1. Open this folder in Antigravity IDE.
1. Supply this prompt to the Agy Agent:
   ```/grill-me Using this folder tree as a template, create the required folder structure 
   in this workspace for my new 'smart-gcp-finops' Python project.
   Only create folders and files that are marked as '*'. 
   For required files, provide initial starter-for-10 content. 
   << paste the tree structure here >>
   ```

Give it a go!

## Skills for Your Coding Agent

I like to describe skills as **units of knowledge that agents load on-demand**, when they need to do a particular task. I've previously articles on the subject of my favourite skills, where to find them, and how to install them. I recommend you check out [this one](todo). You might want to go ahead and install all of my favourites!  

But for now, let's add a few skills that will definitely be useful for our current project. I recommend installing them globally, so they'll be available to all of your development projects.

```bash
npx skills add https://github.com/vercel-labs/skills -y -g --skill find-skills
npx skills add https://github.com/derailed-dash/dazbo-agent-skills -y -g
npx skills add https://github.com/google/skills -y -g
npx skills add https://github.com/google-gemini/gemini-skills/ -y -g
npx skills add https://github.com/shubhamsaboo/awesome-llm-apps/awesome-agent-skills -y -g --skill technical-writer
```

We're also going to install the Google Agents CLI and its associated skill, but we'll get to that later.

## `GEMINI.md` - Context for Your Coding Agent

This is how we tell the Agy Agent:

- Useful stuff about your project's goals
- Rules and guidelines you want it to follow
- References you want it to read

When we create `GEMINI.md` in the root of a project, then the context is scoped only to _that project_. (This project-specific context gets appended to any global `GEMINI.md` you have defined.) 

When you launch any Antigravity tool from this workspace - such as Agy 2.0, IDE, or Antigravity CLI - the Agy Agent will automatically read this context.

Let me show you what my `GEMINI.md` looked like, when starting out with _FinSavant_:

```md
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
[skipping for brevity]

### Gemini Enterprise Agent Platform APIs

- `gemini-api`: Vertex AI, Google Cloud, and Agent Platform enterprise usage with the Google Gen AI SDK.
[skipping for brevity]

### Agent Platform Engine & Model Management

- `agent-platform-deploy`: Deploying models and tuned weights to Agent Platform endpoints.
[skipping for brevity]

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
[skipping for brevity]

## Other Notes

- "Vertex AI" no longer exists as a product; the replacement is Gemini Enterprise Agent Platform.
- "Vertex AI Agent Engine" is no more; the replacement is "Agent Runtime", which is a part of the Gemini Enterprise Agent Platform.
- But APIs and Google internal resource names may still refer to legacy names, e.g. `reasoningEngine` rather than Agent Runtime. Always use the new names when creating documentation, but be mindful that we may need to use old names in API calls and certain resource definitions.

## Blog

I want to build a multi-part blog series, which I'll post on Medium and Dev.to.

### Documenting As We Go

As we go, document steps taken, experience and findings in docs/blog.md. Later, I will build a Medium blog from this content. During this "as we go" phase, the blog.md does not need to be a polished article. It can be a collection of notes, code snippets, and observations. It should:

- Include all the key steps we did, in the order we did them.
[skipping for brevity]

...
```

Give Agy a restart now, so it picks up this context.

## Documentation Approach

I'm a big fan of having a consistent set of high-quality, continuously maintained documentation. I even have my own agent skill - `maintain-core-documentation` - to automate much of this for me. Check out my [previous blog on this subject](todo).

If you ran the `npx skills add https://github.com/derailed-dash/dazbo-agent-skills -y -g` above, then you now already have this skill installed.

With this in place, you could issue a prompt like this to bootstrap a set of documentation for a brand new project:

```text
Use maintain-core-documentation to boostrap my project documentation.
```

As you evolve your project, you can ask the agent to `Maintain core documentation` and it will update as required.

## MCP Servers for Your Coding Agent

I've [previously written about](todo) some of my favourite MCP servers. There's only a couple that we'll need for this project:

- Google BigQuery Remote MCP Server
- My ADK-Docs MCP Server

Note that we won't be using either of these in the _FinSavant_ agent itself. These are purely to help us during development.

Let's try out the BigQuery MCP server...

## Scaffolding Your ADK Agent

The easiest way to scaffold a new ADK agent is to use make use of **Google Agents CLI**. The Agents CLI is actually a bundle, containing:

- The **Agents CLI** itself - commands for scaffolding, evaluating, deploying, and observing AI agents on Google Cloud.
- An associated set of **agent skills** that turn your development agent into an expert in using Agents CLI.

So now we could run the CLI manually...

```bash
command
```

But instead we can now just say to the Agy Agent:

```text
/gill-me Please scaffold a new ADK agent called 'finops_agent'. This root agent should be deployed inside its own 'finops_agent' folder inside the 'app' folder. Do not implement any business logic for the agent.
```

## Getting Started with a Makefile

## Useful Links and References

### Project Demo & Portfolio

- [FinSavant on GitHub](todo_link)
- [FinSavant YouTube Demo](https://youtu.be/zs_IRUxIx4E)
- [Dazbo's Portfolio](https://dazbo.co.uk)

### Gemini Enterprise Agent Platform & ADK

- [Gemini Enterprise Agent Platform Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [ADK Agent Building Guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Agents CLI Documentation](https://google.github.io/agents-cli/?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)

### Google Cloud Services & APIs

- [Google Cloud Assist](https://docs.cloud.google.com/cloud-assist/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Cloud Asset Inventory (CAI) API](https://docs.cloud.google.com/asset-inventory/docs/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Developer Knowledge MCP Server](https://developers.google.com/knowledge/mcp?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)

### Other Related Articles & Resources

- 


