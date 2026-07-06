[x] Create Dev Google Cloud project
[x] Create Prod (CI/CD) Google Cloud project
[x] Create workspace with Agent-Starter-Pack
[x] Initialise git repo
[x] Create .env file
[x] Setup git-crypt
[x] Create env script and .envrc
[x] Create GEMINI.md
[x] Add missing APIs
[x] Initialise Conductor
[x] Create initial docs
[x] Deploy the Control Plane (Prod project) resources using Terraform
[x] Migrate TF state to GCS
[x] Verify manual production deployment via 'Run workflow' in Actions tab
[x] Add DNS to Cloud Run service
[x] Optimise Cloud Run services with min of 0 and max of 1, and sensible CPU / memory
[x] Add IAP to Cloud Run
[x] Setup run-gemini-cli CI/CD
[x] Ensure TF deploy of Cloud Run service does not overwrite gcloud parameters
[x] Add startup CPU boost to Cloud Run services
[x] Add support env var for Google project that hosts Billing Export BQ
[x] Allow Cloud Run service view on BQ billing export dataset
[x] Add BQ Remote MCP to developer workspace
[x] Integrate BigQuery remote MCP into ADK agent logic and test with ADK Web
[x] Integrate Google Asset Inventory search into ADK agent logic and test with ADK Web
[x] Integrate Google Asset Inventory metadata and history enrichment into ADK agent logic
[x] Integrate Google Knowledge MCP API into ADK agent logic and test with ADK Web
[x] Design initial UI using Stitch
[x] Implement the initial UI, using a framework that supports A2UI and a streaming chat interface
[x] Implement A2UI rich components for billing tables and cost charts
[x] Add AI-powered cost forecasting tool to the agent logic
[x] Implement anomaly detection triggers and notification system
[x] Finalise the React dashboard with Stitch-accelerated components
[x] Make tool usage feedback in chat window more "user friendly"
[x] Add more sample questions to the chatbot
[x] Overhaul and refactor for ADK 2 and update packages
[x] Use fast model to check if a question has semantic same meaning as a previous question and cache response
[x] Test in single unified container locally
[x] Deploy and test on Cloud Run, and ensure it works with IAP
[x] Setup continuous deployment (CI/CD) of the frontend and backend
[x] Cache repeating queries, e.g. duplicate queries for zombie resources.
[x] Migrate to Gemini Enterprise Agent Runtime, with UI in separate Cloud Run
[x] Swap out BigQuery MCP in the agent to use ADK native BigQueryToolset. Update blog accordingly; we still use MCP from our dev environment, but not in the agent.
[x] Remove env var redundancy in architecture walkthrough md
[x] Bootstrap new ADK agent folder with agents-cli
  - [x] Delete existing empty `app` directory to allow clean bootstrapping.
  - [x] Run `agents-cli scaffold create app` as a prototype with `GEMINI.md` guidance.
  - [x] Create `docs/agent-bootstrap.md` to track bootstrapping, migration, and deployment progress.
  - [x] Implement up-front project discovery in `before_agent_callback` and save to ADK session state.
  - [x] Adapt/re-implement business logic from `app-old` (zombie resources, CAI tools, BigQuery SQL caching) to retrieve scoping configuration from ADK state.
  - [x] Run local smoke tests (`agents-cli run`) to verify agent and tool execution.
  - [x] Clean separation of BFF and Agent with separate deployable Dockerfiles
  - [x] Verify local BFF and Agent work together
  - [x] Verify unified container build still works
  - [x] Update documentation to reflect clean separation
  - [x] Deploy/enhance to Agent Runtime once validated.
  - [x] Update Terraform and CI/CD to ensure all is working.
[x] Fix Vertex branding in UI
[x] Implement API rate limiting
[x] Update Terraform variables and CI/CD pipelines to ensure `google_cloud_location` / `GOOGLE_CLOUD_LOCATION` is explicitly set to `"global"` to prevent regional Gemini model routing errors (like 404 on `gemini-3.5-flash`).
[~] Create blog series
  - [x] Arch diagram should show the Agent running in Agent Runtime, MCPs and other tools, and Agent Registry link
  - [x] Blog part 1
  - [~] Blog part 2
  - [ ] Blog part 3
  - [ ] Blog part 4
  - [ ] Blog part 5
  - [ ] Blog part 6
  - [ ] Blog part 7
[ ] Convert arch diagrams to renders
[x] Create a UI/BFF-only Dockerfile for Cloud Run; keep the unified for local
[ ] Ensure best-practices query is always aligned to deployed services and costs; not generic
[ ] Separate monolithic prompt with subagents
[ ] Perform ADK best practices review
[ ] Introduce ADK based evaluation, including trajectory.
[ ] (Future Phase) Implement Dynamic Server-Side Chart Rendering (PNG) for text-centric channels like Gemini Enterprise
