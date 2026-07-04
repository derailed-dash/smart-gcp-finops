locals {
  cicd_services = [
    "cloudbuild.googleapis.com",
    "aiplatform.googleapis.com",
    "serviceusage.googleapis.com",
    "bigquery.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "cloudtrace.googleapis.com",
    "telemetry.googleapis.com",
    "artifactregistry.googleapis.com",
    "agentregistry.googleapis.com",
  ]

  deploy_project_services = [
    "cloudaicompanion.googleapis.com",
    "aiplatform.googleapis.com",
    "geminicloudassist.googleapis.com",
    "run.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "iam.googleapis.com",
    "bigquery.googleapis.com",
    "storage.googleapis.com",
    "serviceusage.googleapis.com",
    "logging.googleapis.com",
    "cloudtrace.googleapis.com",
    "monitoring.googleapis.com",
    "telemetry.googleapis.com",
    "iap.googleapis.com",
    "cloudbilling.googleapis.com",
    "cloudasset.googleapis.com",
    "developerknowledge.googleapis.com",
    "agentregistry.googleapis.com",
  ]


  deploy_project_ids = {
    prod    = var.prod_project_id
    staging = var.staging_project_id
  }

  all_project_ids = [
    var.cicd_runner_project_id,
    var.prod_project_id,
    var.staging_project_id
  ]

  app_domain_names = {
    prod    = var.prod_app_domain_name
    staging = var.staging_app_domain_name
  }

  cloud_run_min_instances = {
    prod    = var.cloud_run_prod_min_instances
    staging = var.cloud_run_staging_min_instances
  }

  cloud_run_max_instances = {
    prod    = var.cloud_run_prod_max_instances
    staging = var.cloud_run_staging_max_instances
  }

  agent_runtime_min_instances = {
    prod    = var.agent_runtime_prod_min_instances
    staging = var.agent_runtime_staging_min_instances
  }

  agent_runtime_max_instances = {
    prod    = var.agent_runtime_prod_max_instances
    staging = var.agent_runtime_staging_max_instances
  }

  agent_name = "finops_agent"

  agent_runtime_cpu    = "1"
  agent_runtime_memory = "4Gi"

  # Parse app/.env file to get variables
  env_content = fileexists("${path.module}/../../app/.env") ? file("${path.module}/../../app/.env") : ""
  
  # Parse key-value pairs from env_content (ignoring comments and empty lines)
  env_lines = [
    for line in split("\n", local.env_content) :
    trimspace(line)
    if trimspace(line) != "" && !startswith(trimspace(line), "#") && length(split("=", line)) > 1
  ]
  
  env_map = {
    for line in local.env_lines :
    trimspace(split("=", line)[0]) => trimspace(substr(line, length(split("=", line)[0]) + 1, -1))
  }
}

