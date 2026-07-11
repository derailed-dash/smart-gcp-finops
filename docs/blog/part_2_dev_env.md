# FinSavant Part 2: Building an Agentic FinOps Platform - Development Environment Setup, Google Antigravity, MCPs and Skills, and ADK Bootstrapping with Agents CLI

**TL;DR - This article is going to be jam-packed with useful information, tips, tricks and hacks for setting up an agentic development in the Google ecosystem.**

This one isn't really about the Fin Ops!

## Welcome to Part 2

![Dr Evil Back](../images/dr-evil-back.png)

Welcome back, friends!

In the [first part](https://medium.com/google-cloud/finsavant-part-1-building-an-agentic-finops-platform-with-google-adk-a2ui-and-gemini-enterprise-248f59cea3a0), I described the purpose of the [FinSavant](https://github.com/derailed-dash/smart-gcp-finops) FinOps solution, the motivation for creating it, its overall architecture and tech stack, and how it works.

In this part, we'll use _FinSavant_ as a case study in **how to set up a development environment** for the purposes of building such an ADK-based agentic solution. **Even if you're not particularly interested in _FinSavant_ itself, I hope you'll find a bunch of useful information and tips here that will help you build your own agentic solutions more effectively and quickly.**

We'll cover:

1. Using Antigravity IDE
1. Overall project workspace structure
1. Setting up agent skills for your coding agent
1. My project's `GEMINI.md` (or if you prefer, `AGENTS.md`)
1. My documentation approach
1. Setting up MCP servers for your coding agent, such as BigQuery MCP
1. Scaffolding the initial ADK agent using Google Agents CLI and its supporting skill
1. Getting started with a Makefile

Sound good? Let's get cracking!

## Series Orientation

Let's see where we are in this series.

1. Goals, Architecture, and Tech Stack: Capabilities, project goals, target architecture, technology stack, and design decisions.
2. Development Environment Setup, Google Antigravity, MCPs and Skills, and ADK Bootstrapping with Agents CLI **📍 You are here.**
3. Building the ADK Agent and API
4. Designing and Building the UI with Google Stitch and A2UI
5. Deployment with Gemini Enterprise Agent Platform, Agent Runtime, Cloud Run and IAP
6. Automating Deployment with CI/CD and Terraform
7. Agent Observability, Evaluation, and Tuning with Gemini Enterprise Agent Platform

## Getting Started with Antigravity IDE

These days, my favourite coding environment _for any significant project_ is Antigravity IDE. This is Google's _agent-first_ integrated development environment. You get a look-and-feel that's familiar to VS Code users, but powered with autonomous, context-aware agents that can plan, execute, verify, and work in parallel.

You can get it [here](https://antigravity.google/product/antigravity-ide?utm_campaign=DEVECO_GDEMembers&utm_source=deveco).

By the way, Antigravity IDE is just one member of the Antigravity (aka Agy) suite. 

![The Antigravity Suite](../images/agy-suite-all.jpg)

I've covered these before, but here's a quick reminder of the four Agy solutions in the suite:

- **Antigravity 2.0**, which is now the dedicated agent-first “builder” environment on your desktop. Notably, it doesn’t itself include an IDE. Instead, we now interact only with the agent manager. This surface aims to usher in the era of “idea to product” using agents, without concerning ourselves over the code. Many builders who don’t come from a coding background will love this.
- **Antigravity IDE**, which gives us the more familiar VS Code-esque coding environment, supported by the Antigravity agent harness. Here we can do agent-assisted development, and we always see the code. Coders will feel at home here.
- **Antigravity SDK**, which gives you the harness and tools that power Antigravity, but exposed as a Python Agent SDK. By importing from google.antigravity we can programmatically leverage Antigravity’s capabilities.
- **Antigravity CLI**, which is the next evolution of the extremely awesome Gemini CLI. It’s still a terminal-first environment for interacting with Gemini models. But the new Antigravity CLI is built in Go, and you can tell; it feels much faster than Gemini CLI, both during startup and in general use. It leverages the same agent “harness” as Antigravity 2.0 and the IDE, and this allows for common settings and configuration across the Antigravity suite.

## Project Structure

Here's the rough outline of the project structure we'll be creating. We won't be building all of this structure here; nor does this represent the final state of the project. But it gives you an idea of where we're heading. (I'll explain the `*` in a minute!)

```text
  smart-gcp-finops/
  ├── agent/                # ADK agent package
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
* ├── .agents/            # Workspace customizations root
  │   └── mcp_config.json   # E.g. MCP servers
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

1. Create your new project folder, e.g. `my-cool-project`
1. Open that folder in Antigravity IDE.
1. Supply this prompt to the Agy Agent:

   ```/grill-me Using this folder tree as a template, create the 
   required folder structure in this workspace for my new Python project.
   Only create folders and files that are marked as '*'. 
   For required files, provide initial starter-for-10 content. 
   << paste the tree structure here >>
   ```

Why `/grill-me`? This is a built-in Agy command that causes the agent to ask questions to remove ambiguity. If you were to give the agent a slightly vague prompt without this prefix, then the agent might make some guesses about what you want. But with `/grill-me`, the agent will still make educated guesses, but it will also ask you questions to clarify your intent.

The prompt above is a good example of where this is useful. You'll notice that my project tree has a `LICENSE.md` file, which is a standard component to include in open-source projects. But my prompt doesn't specify which license to use. So when you use `/grill-me`, the agent will offer sensible license choices based on your project and context, and ask you to confirm.

This video demonstrates Agy scaffolding the entire project from scratch, in response to the prompt above:
[![Agy Scaffolding Demo](https://img.youtube.com/vi/DmnBHilRjOo/maxresdefault.jpg)](https://youtu.be/DmnBHilRjOo?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)

Give it a go!

## Skills for Your Coding Agent

I like to describe skills as **units of knowledge that agents load on-demand**, when they need to do a particular task. I've previously written articles on the subject of my favourite skills, where to find them, and how to install them. I recommend you check out [this one](https://medium.com/google-cloud/dialling-our-agents-to-11-agent-skills-you-need-to-be-using-ccffa51e91df). You might want to go ahead and install all of my favourites!  

But for now, let's add a few skills that will definitely be useful for our current project. I recommend installing them globally, so they'll be available to all of your development projects.

```bash
npx skills add https://github.com/vercel-labs/skills -y -g --skill find-skills
npx skills add https://github.com/derailed-dash/dazbo-agent-skills -y -g
npx skills add https://github.com/google/skills -y -g
npx skills add https://github.com/google-gemini/gemini-skills/ -y -g
npx skills add https://github.com/shubhamsaboo/awesome-llm-apps/awesome-agent-skills -y -g --skill technical-writer
```

We're also going to install the _Google Agents CLI_ and its associated skills, but we'll get to that later.

## `GEMINI.md` - Context for Your Coding Agent

The `GEMINI.md` file (or `AGENTS.md` if you prefer) is how you define your project's rules and context.  It's where you tell the Agy Agent:

- About your project's goals
- Rules and guidelines you want it to follow
- References you want it to read

When we create `GEMINI.md` in the root of a project then the file is scoped only to _that project_. (This project-specific context gets appended to any global `GEMINI.md` you have defined.) When you launch any Antigravity tool from this workspace - such as Agy 2.0, Agy IDE, or Agy CLI - the Agent will automatically read this context.

Let me show you what my `GEMINI.md` looked like, when starting out with _FinSavant_:

```md
# FinSavant - the Agentic FinOps Solution

## Project Goals

To create an agentic FinOps solution for GCP that:

- Uses ADK for agent orchestration.
- Is able to examine billing and cost data in BigQuery, based on billing exports.
- Is able to understand Google Cloud infrastructure and services across multiple Google projects associated with a billing account.
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
- The Agent will be deployed to Agent Runtime in Gemini Enterprise Agent Platform.

## Tool Use: Skills, Gemini Enterprise Agent Platform, Agent Runtime and ADK

Be sure to use all **agents** skills, **Gemini Enterprise Agent Platform** skills, and **ADK** skills you have available for developing ADK agents and best practices, and use **adk-docs-mcp** for latest ADK documentation. 

You will have additional skills available to you, but always check if the following can help with a particular task.

### ADK & agents-cli Lifecycle Skills

- `google-agents-cli-workflow`: Entrypoint for building ADK agents (scaffold, build, evaluate, deploy, publish, observe).
[skipping for brevity]

### Gemini Enterprise Agent Platform APIs

- `gemini-api`: Gemini Enterprise Agent Platform, Google Cloud, and Agent Platform enterprise usage with the Google Gen AI SDK.
[skipping for brevity]

### Agent Platform Engine & Model Management

- `agent-platform-deploy`: Deploying models and tuned weights to Agent Platform endpoints.
[skipping for brevity]

## Key Internal Documentation

- README.md - Project README; the developer's front door
- TODO.md - High level plan for the project
- architecture-and-walkthrough.md - The main architecture, including design decisions
- DESIGN.md - Where we will capture the UI design
- testing.md - Where we will document test strategy, summary of tests, testing instructions, any manual testing processes
- docs/blog.md - A blog post document we will build along the way
- /deployment/README.md - Deployment and CI/CD documentation

## Essential Reading

You should read and leverage these resources for guidance and best practices, in addition to the skills and MCP servers you have available for knowledge.

| Resource | Description and Relevance |
| -------- | ------------------------- |
| https://docs.cloud.google.com/bigquery/docs/use-bigquery-mcp?utm_campaign=DEVECO_GDEMembers&utm_source=deveco | Use the BigQuery MCP server | 
| https://adk.dev/integrations/bigquery/?utm_campaign=DEVECO_GDEMembers&utm_source=deveco | BigQuery tool for ADK |
| https://docs.cloud.google.com/gemini-enterprise-agent-platform?utm_campaign=DEVECO_GDEMembers&utm_source=deveco | Gemini Enterprise Agent Platform Overview |
| https://adk.dev/deploy/agent-runtime?utm_campaign=DEVECO_GDEMembers&utm_source=deveco | ADK with Agent Runtime |
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

If you're following along and you've just created your context file, give Agy a restart now, so it picks this up.

## Documentation Approach

I'm a big fan of having a consistent set of high-quality, continuously maintained documentation. I even have my own agent skill - `maintaining-core-documentation` - to automate much of this for me. Check out my previous blog on this subject: [Documentation as Context: A Skill to Automate Your Blueprints for the Agentic Era](https://medium.com/google-cloud/documentation-as-context-a-skill-to-automate-your-blueprints-for-the-agentic-era-2bec0cf041a3).

If you previously ran the `npx skills add https://github.com/derailed-dash/dazbo-agent-skills -y -g` command from above, then you already have this skill installed.

With this in place, you could issue this prompt to bootstrap a set of documentation for a brand-new project:

```text
Use maintaining-core-documentation to bootstrap my project documentation.
```

Check out this video to see the skill doing its magic!

[![Documentation Skill Demo](https://img.youtube.com/vi/fvT_GJ4LPhE/maxresdefault.jpg)](https://youtu.be/fvT_GJ4LPhE?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)

As you evolve your project, this skill will automatically maintain your documentation.

## MCP Servers for Your Coding Agent

I've previously written about [some of my favourite MCP servers](https://medium.com/google-cloud/dialling-our-agents-to-11-my-favourite-mcp-servers-9549c1442a5e). There are only a couple that we'll need for this project:

- [Google BigQuery Remote MCP Server](https://docs.cloud.google.com/bigquery/docs/use-bigquery-mcp?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [ADK Docs MCP](https://adk.dev/tutorials/coding-with-ai/?utm_campaign=DEVECO_GDEMembers&utm_source=deveco#adk-docs-mcp-server)

Note that we won't be using either of these in the _FinSavant_ agent itself. These are purely to help us during development.

Let's try out the BigQuery MCP server first. In your workspace's `.agents/mcp_config.json` file, we configure the **Remote BigQuery MCP server** like this:

```json
{
  "mcpServers": {
    "bigquery-mcp-server": {
      "serverUrl": "https://bigquery.googleapis.com/mcp",
      "authProviderType": "google_credentials",
      "oauth": {
        "scopes": [
          "https://www.googleapis.com/auth/bigquery"
        ]
      },
      "headers": {
        "x-goog-user-project": "your-gcp-billing-project"
      }
    }
  }
}
```

A few things to note about this:

- **Billing project**: Replace `your-gcp-billing-project` with the Google project where your billing data export lives.

    ![BQ Billing Dataset in the Cloud Console](../images/bq_billing_dataset_console.png)

- **BigQuery API**: Make sure the BigQuery API (`bigquery.googleapis.com`) is enabled on that project.
- **Developer Identity Permissions**: Because the MCP server uses `google_credentials` to authenticate, your local developer account (active in `gcloud auth`) must be authorised on Google Cloud. You need the `roles/bigquery.dataViewer` and `roles/bigquery.jobUser` roles on the project hosting the billing dataset.  
- You also need the `roles/mcp.toolUser` role, in order to use this managed MCP server to query the BigQuery database.

And now, when you open the workspace in Antigravity IDE, it will load this configuration automatically. Your coding agent will be able to query schemas, inspect tables, and try out SQL queries in order to assist you when you actually create the _FinSavant_ agent code.

Let's test it!

First, I issue this prompt to the Agy agent:

```text
What billing tables do I have? Explain their key functions.
```

![What billing tables do I have?](../images/what-billing-tables.png)

You can see the agent immediately finds the MCP server and asks for permission to invoke its tools. After I grant permission, I get this response:

![BQ MCP response](../images/bq-mcp-response.png)

Nice! You can see how helpful this is going to be.

## Scaffolding Your ADK Agent

The easiest way to scaffold a new ADK agent is to make use of **Google Agents CLI**. The Agents CLI is actually a bundle, containing:

- The **Agents CLI** itself - commands for scaffolding, evaluating, deploying, and observing AI agents on Google Cloud. The [GitHub repo](https://github.com/google/agents-cli) describes the commands available:

  ![agents-cli commands](../images/agents-cli-commands.png)

- An associated set of **agent skills** that turn your development agent into an expert in using Agents CLI.

  ![agents-cli skills](../images/agents-cli-skills.png)

You install the bundle using this one-time command:

```bash
uvx google-agents-cli setup
```

If you already have it installed, then you can upgrade like this:

```bash
uv tool upgrade google-agents-cli
```

(It's worth doing this occasionally - this CLI is evolving quickly!)

With this installed, we _could_ create our top level `agent` folder that contains a root agent called `finops_agent` by running this command:

```bash
agents-cli scaffold create agent \
  --agent adk \
  --prototype \
  --agent-directory finops_agent 
```

![agents-cli create](../images/adk-create.png)

You'll end up with the following inside of your workspace folder:

```text
agent/
├── finops_agent/                 # Your agent code
│   ├── __init__.py               # Registers the app (exports `app`)
│   ├── agent.py                  # Agent definition — instructions, model, tools
│   └── app_utils/                # Utilities (telemetry, converters)
│       ├── __init__.py
│       ├── telemetry.py          # OpenTelemetry setup for Cloud Trace
│       ├── typing.py             # Request/response Pydantic models
│       └── gcs.py                # GCS utility functions
│
├── tests/
│   ├── eval/                     # Evaluation test cases
│   │   ├── datasets/
│   │   │   └── basic-dataset.json    # Default eval cases
│   │   └── eval_config.yaml          # Evaluation metrics configuration
│   ├── integration/
│   │   └── test_agent.py         # Integration test (runs agent end-to-end)
│   └── unit/
│       └── test_dummy.py         # Placeholder for unit tests
│
├── .env                          # Environment variables (project ID, location)
├── .env.example                  # Example environment variables
├── .gitignore                    # Git ignore file
├── pyproject.toml                # Project config and dependencies
├── agents-cli-manifest.yaml      # Configuration for agents-cli
├── Dockerfile                    # Dockerfile for the agent runtime
└── GEMINI.md                     # Guidance file for coding agents
```

But since we now have the skills installed, there's an easier way to accomplish this, that doesn't require you to check the CLI documentation...

```text
Please bootstrap a new ADK agent project. The agent top-level project should be named `agent`, and it should contain a root `agent-directory` called `finops_agent`, NOT the default of `app`. This means `pyproject.toml` and other config files will live under `agent/`, and all Python source files (like `agent.py` and `fast_api_app.py`) will live inside `agent/finops_agent/`.
```

Sure, this prompt is quite detailed, but I'm after a very specific folder structure.

Let's see a live demo...

[![Agents-CLI ADK scaffolding demo](https://img.youtube.com/vi/wxMK7MKwHqA/maxresdefault.jpg)](https://youtu.be/wxMK7MJwHqA?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)

As you can see from the demo, we can now use `agents-cli` to check if our newly scaffolded agent is working.

For example, by issuing a single test prompt on the command line:

```bash
cd agent
agents-cli run "Hello! Who are you?"
```

![agents-cli run](../images/agents-cli-run.png)

Or, we could run up the extremely powerful and useful **ADK Web** interface, using this handy shortcut:

```bash
# From the agent folder
agents-cli playground
```

![agents-cli playground](../images/agents-cli-adk-web.png)

Concluding thought about `Agents-CLI`: if you know your way around the CLI, you can use it directly. It'll be faster and use fewer tokens. But when you're doing lots of agent related activities like boostrapping, adding CI/CD, deploying and evaluating, you'll probably find that natural language conversations are going to save you a lot of time and pain.

## Bonus #1: Getting Started with a Makefile

In a "monorepo" project setup like _FinSavant_, you quickly end up managing a lot of moving parts: building frontend assets, compiling Python environments, building and running multiple Docker images, executing test suites, and deploying resources to various target environments. 

Rather than forcing yourself (or your team) to remember a massive list of commands and flags, wrapping them in a `Makefile` is a big win. 

But what actually is a `Makefile`? At its core, it is a configuration file used by the classic `make` build automation tool. These days it has evolved into a lightweight, standardised task runner. It allows us to define short aliases (known as "targets") for complex shell commands, documenting project workflows in a single, standard file that is easy for both humans and agents to discover.

Earlier, during the demonstration of bootstrapping the project, the agent actually created an initial `Makefile` for us. If you followed along, you'll now have a `Makefile` that looks something like this:

```makefile
.PHONY: install lint format lint-fix test

install:
	@command -v uv >/dev/null 2>&1 || { echo "uv is not installed. Installing uv..."; curl -LsSf https://astral.sh/uv/0.11.16/install.sh | sh; source $HOME/.local/bin/env; }
	uv sync

lint:
	uvx codespell@latest -s
	uvx ruff@latest check .

lint-fix:
	uvx codespell@latest -w
	uvx ruff@latest check --fix .

test:
	uv run pytest tests/
```

Now you can run any of these `make` _targets_, like this:

```bash
make install
```

With this in place, we can build on it in future articles as we develop the _FinSavant_ solution.

## Bonus #2: My Setup-Env Script

These days, whenever I'm working on a project that makes use of Google services, I always create a helper `setup-env` script to configure my environment for me.

This script:

1. **Loads environment variables**: Automatically exports all key/value pairs from `.env` directly into the current shell session.
2. **Handles Google Cloud authentication**: If not skipped (via the `--noauth` flag), it runs `gcloud auth login --update-adc` to authenticate the user and configure Google Application Default Credentials (ADC).
3. **Sets the active gcloud project**: Configures `gcloud` defaults for the target project and billing quota project settings.
4. **Extracts project metadata**: Dynamically retrieves the Google Cloud Project Number and constructs helper variables (like the Cloud Build service account email) for deployment scripts.
5. **Synchronises Python dependencies**: Runs `uv sync` to ensure all standard, development, and notebook dependencies are installed in the local environment.
6. **Activates the virtual environment**: Activates the local Python virtual environment (`.venv`) so the user is immediately ready to run code.

You can find a copy of this `scripts/setup-env.sh` in my [GitHub repository](https://github.com/derailed-dash/smart-gcp-finops/blob/main/scripts/setup-env.sh). Because it uses standard environment variables defined in your `.env`, you can use it in any of your Google projects!

You run it from the project root directory like this:

```bash
source scripts/setup-env.sh
```

## Bonus #3: Automating Setup with `direnv` and `.envrc`

If you haven't come across this before, I think you're going to like it!

Manually sourcing the `setup-env.sh` script every time I open a terminal in the project directory is a bit of a chore. To automate this, we can use `direnv` — an extension for your shell that automatically runs custom scripts and loads / unloads environment variables depending on your current directory.

By placing a `.envrc` file at the root of the project, `direnv` automatically executes it whenever you `cd` into the directory. 

Here is what our `.envrc` looks like:

```bash

```

This configuration does a few smart things:
1. **Bootstraps the virtual environment**: Automatically initialises a virtual environment using `uv venv` if it doesn't already exist.
2. **Verifies active Google session**: Runs `gcloud auth print-access-token` silently to check if our Google Cloud session is active.
3. **Conditionally sources configuration**: If the Google Cloud session is still valid, it sources the setup-env script with the `--noauth` flag, avoiding repetitive and annoying browser login prompts. If the session has expired, it triggers the full setup script to re-authenticate.

There are a couple of one-off steps we have to do to get `direnv` up and running:

1. Install `direnv`. On Debian/Ubuntu systems, this is `sudo apt install direnv`.
2. Allow _this_ folder for `direnv`. Run `direnv allow` in the terminal, in the project folder where we've placed our `.envrc` file.

Now, when we enter our project folder, the script runs automatically, like this:

![running direnv](../images/direnv-demo.gif)

Pretty neat, right?

## Wrap-Up and Next Steps

Okay, we're done with the environment setup. We've:

- Setup Google Antigravity, along with some killer skills and MCP servers
- Bootstrapped our project using the Agy agent
- Played with `/grill-me`
- Established an initial set of core project documentation, using a custom skill
- Used the Agy agent to bootstrap an ADK agent, making use of `agents-cli` and its skills
- Created a `Makefile` for standardising common development, testing and deployment tasks
- Created a `scripts/setup-env.sh` script for setting up our Google Cloud environment
- Used `direnv` and a `.envrc` file to automate the setup process, every time we open a terminal in this directory

In the next part, we'll look at the actual code for our _FinSavant_ agents and tools!

See you there!

## Useful Links and References

### Project Demo & Portfolio

- [FinSavant on GitHub](https://github.com/derailed-dash/smart-gcp-finops)
- [FinSavant YouTube Demo](https://youtu.be/zs_IRUxIx4E?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Dazbo's Portfolio](https://dazbo.co.uk)

### Gemini Enterprise Agent Platform & ADK

- [Gemini Enterprise Agent Platform Overview](https://docs.cloud.google.com/gemini-enterprise-agent-platform/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [ADK Agent Building Guide](https://docs.cloud.google.com/gemini-enterprise-agent-platform/build/adk?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Agents CLI on GitHub](https://github.com/google/agents-cli?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Agents CLI Documentation](https://google.github.io/agents-cli/?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)

### Google Cloud Services & APIs

- [Google Cloud Assist](https://docs.cloud.google.com/cloud-assist/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Cloud Asset Inventory (CAI) API](https://docs.cloud.google.com/asset-inventory/docs/overview?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Developer Knowledge MCP Server](https://developers.google.com/knowledge/mcp?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)

### Other Related Articles & Resources

- [Antigravity IDE Documentation](https://antigravity.google/product/antigravity-ide?utm_campaign=DEVECO_GDEMembers&utm_source=deveco)
- [Makefile Tutorial](https://makefiletutorial.com/) - A modern, visual guide to writing GNU Makefiles.
- [uv Package Manager](https://astral.sh/uv) - Fast Python package manager and resolver.
- [Ruff Linter & Formatter](https://docs.astral.sh/ruff/) - Blazing fast linter and formatter for Python.

