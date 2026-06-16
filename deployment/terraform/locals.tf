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
    "telemetry.googleapis.com",
    "iap.googleapis.com",
    "cloudbilling.googleapis.com",
    "cloudasset.googleapis.com",
    "developerknowledge.googleapis.com",
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

  min_instances = {
    prod    = var.prod_min_instances
    staging = var.staging_min_instances
  }

  max_instances = {
    prod    = var.prod_max_instances
    staging = var.staging_max_instances
  }
}

