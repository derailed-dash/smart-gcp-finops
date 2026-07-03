I'm on holiday, catching up on blogging my latest experiment: **FinSavant**, an agentic FinOps virtual analyst for GCP. 🏖️

Built with Google's ADK (Agent Development Kit) and deployed to serverless Agent Runtime on Gemini Enterprise Agent Platform, it combines:
- 📈 BigQuery billing data
- 🛠️ Cloud Asset Inventory (for config drift/spike root cause analysis)
- ⚡ Google Cloud Assist (for live metrics, logs & recommenders)
- 📚 Developer Knowledge MCP (for grounded GCP best practices)

Rather than static dashboards, it uses **Agent-to-UI (A2UI)** to dynamically generate JSON UI layouts (charts, tables, cards) rendered on-the-fly in React depending on user context.

I've just published **Part 1**, focusing on the **Goals, Architecture, and Tech Stack**. I break down:
- 🏗️ **Decoupled Architecture:** React + FastAPI + ADK Agent.
- 🔀 **Intelligent Tool Routing:** Dynamic routing across APIs and MCP servers.
- 🛡️ **Identity-Aware Security:** Row-level BigQuery filtering tied to user IAP identity.
- 🚀 **Serverless Infrastructure:** Securing Cloud Run with native IAP, and Agent Runtime.
- ⚡ **Semantic & Context Caching:** Slashing turn latency/costs using Gemini system caching and a fast classifier model (`gemini-3.1-flash-lite`) to bypass heavy BQ/LLM queries for repeated questions.

Deploying to Agent Runtime was a proper journey. I fought Hatchling packaging quirks, container path mismatches, and REST routing issues. Honestly, I only got it over the line thanks to my Antigravity skills and local MCPs helping me diagnose Cloud Logging traces and guiding me through the troubleshooting.

Upcoming in the series: 
- Part 2 - Dev setup, agent coding, and deployment
- Part 3 - React and A2UI
- Part 4 - Terraform & CI/CD
- Part 5 - Evaluation & tuning

FinSavant scales across organisations and projects. It's not fully enterprise-ready yet, but getting there. It's open source — collaboration welcome!

- 🔗 Medium article: https://medium.com/google-cloud/finsavant-part-1-building-an-agentic-finops-platform-with-google-adk-a2ui-and-gemini-enterprise-248f59cea3a0
- 🔗 Dev.to article: https://dev.to/gde/finsavant-part-1-building-an-agentic-finops-platform-with-google-adk-a2ui-and-gemini-enterprise-29l3
- 📽️ YouTube demo: https://www.youtube.com/watch?v=zs_IRUxIx4E&feature=youtu.be
- 💻 GitHub repo: https://github.com/derailed-dash/smart-gcp-finops

#GoogleCloud #GeminiEnterpriseAgentPlatform #AgentRuntime #Antigravity #GenerativeAI #ADK #FinOps #CloudRun #FastAPI #A2UI #AgentSkills #MCP #CloudAssist #GDE #GoogleCloudAmbassador