# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

provider "github" {
  owner = var.repository_owner
}

# Try to get existing repo
data "github_repository" "existing_repo" {
  count     = var.create_repository ? 0 : 1
  full_name = "${var.repository_owner}/${var.repository_name}"
}

# Only create GitHub repo if create_repository is true
resource "github_repository" "repo" {
  count       = var.create_repository ? 1 : 0
  name        = var.repository_name
  description = "Repository created with goo.gle/agent-starter-pack"
  visibility  = "private"

  has_issues    = true
  has_wiki      = false
  has_projects  = false
  has_downloads = false

  allow_merge_commit = true
  allow_squash_merge = true
  allow_rebase_merge = true

  auto_init = false
}


resource "github_actions_variable" "gcp_project_number" {
  repository    = var.repository_name
  variable_name = "GCP_PROJECT_NUMBER"
  value         = data.google_project.cicd_project.number
  depends_on    = [github_repository.repo]
}

resource "github_actions_secret" "wif_pool_id" {
  repository      = var.repository_name
  secret_name     = "WIF_POOL_ID"
  plaintext_value = google_iam_workload_identity_pool.github_pool.workload_identity_pool_id
  depends_on      = [github_repository.repo, data.github_repository.existing_repo]
}

resource "github_actions_secret" "wif_provider_id" {
  repository      = var.repository_name
  secret_name     = "WIF_PROVIDER_ID"
  plaintext_value = google_iam_workload_identity_pool_provider.github_provider.workload_identity_pool_provider_id
  depends_on      = [github_repository.repo, data.github_repository.existing_repo]
}

resource "github_actions_secret" "gcp_service_account" {
  repository      = var.repository_name
  secret_name     = "GCP_SERVICE_ACCOUNT"
  plaintext_value = google_service_account.cicd_runner_sa.email
  depends_on      = [github_repository.repo, data.github_repository.existing_repo]
}

resource "github_actions_variable" "staging_project_id" {
  repository    = var.repository_name
  variable_name = "STAGING_PROJECT_ID"
  value         = var.staging_project_id
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "prod_project_id" {
  repository    = var.repository_name
  variable_name = "PROD_PROJECT_ID"
  value         = var.prod_project_id
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "region" {
  repository    = var.repository_name
  variable_name = "REGION"
  value         = var.google_cloud_region
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "cicd_project_id" {
  repository    = var.repository_name
  variable_name = "CICD_PROJECT_ID"
  value         = var.cicd_runner_project_id
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "app_sa_email_staging" {
  repository    = var.repository_name
  variable_name = "APP_SA_EMAIL_STAGING"
  value         = google_service_account.app_sa["staging"].email
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "app_sa_email_prod" {
  repository    = var.repository_name
  variable_name = "APP_SA_EMAIL_PROD"
  value         = google_service_account.app_sa["prod"].email
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "app_service_account_staging" {
  repository    = var.repository_name
  variable_name = "APP_SERVICE_ACCOUNT_STAGING"
  value         = google_service_account.app_sa["staging"].email
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "app_service_account_prod" {
  repository    = var.repository_name
  variable_name = "APP_SERVICE_ACCOUNT_PROD"
  value         = google_service_account.app_sa["prod"].email
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "logs_bucket_name_staging" {
  repository    = var.repository_name
  variable_name = "LOGS_BUCKET_NAME_STAGING"
  value         = google_storage_bucket.logs_data_bucket[var.staging_project_id].name
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "logs_bucket_name_prod" {
  repository    = var.repository_name
  variable_name = "LOGS_BUCKET_NAME_PROD"
  value         = google_storage_bucket.logs_data_bucket[var.prod_project_id].name
  depends_on    = [github_repository.repo]
}


resource "github_actions_variable" "container_name" {
  repository    = var.repository_name
  variable_name = "CONTAINER_NAME"
  value         = var.project_name
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "artifact_registry_repo_name" {
  repository    = var.repository_name
  variable_name = "ARTIFACT_REGISTRY_REPO_NAME"
  value         = google_artifact_registry_repository.repo-artifacts-genai.repository_id
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "google_cloud_billing_project" {
  repository    = var.repository_name
  variable_name = "GOOGLE_CLOUD_BILLING_PROJECT"
  value         = var.google_cloud_billing_project
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "billing_export_dataset" {
  repository    = var.repository_name
  variable_name = "BILLING_EXPORT_DATASET"
  value         = var.billing_export_dataset
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "google_cloud_billing_account" {
  repository    = var.repository_name
  variable_name = "GOOGLE_CLOUD_BILLING_ACCOUNT"
  value         = var.billing_account_id
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "google_cloud_billing_location" {
  repository    = var.repository_name
  variable_name = "GOOGLE_CLOUD_BILLING_LOCATION"
  value         = var.billing_export_location
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "google_genai_use_vertexai" {
  repository    = var.repository_name
  variable_name = "GOOGLE_GENAI_USE_VERTEXAI"
  value         = tostring(var.google_genai_use_vertexai)
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "google_cloud_location" {
  repository    = var.repository_name
  variable_name = "GOOGLE_CLOUD_LOCATION"
  value         = var.google_cloud_location
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "model" {
  repository    = var.repository_name
  variable_name = "MODEL"
  value         = var.model
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "fast_model" {
  repository    = var.repository_name
  variable_name = "FAST_MODEL"
  value         = var.fast_model
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "google_cloud_organization" {
  repository    = var.repository_name
  variable_name = "GOOGLE_CLOUD_ORGANIZATION"
  value         = var.google_cloud_organization_id
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "cloud_run_staging_min_instances" {
  repository    = var.repository_name
  variable_name = "CLOUD_RUN_STAGING_MIN_INSTANCES"
  value         = tostring(var.cloud_run_staging_min_instances)
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "cloud_run_staging_max_instances" {
  repository    = var.repository_name
  variable_name = "CLOUD_RUN_STAGING_MAX_INSTANCES"
  value         = tostring(var.cloud_run_staging_max_instances)
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "cloud_run_prod_min_instances" {
  repository    = var.repository_name
  variable_name = "CLOUD_RUN_PROD_MIN_INSTANCES"
  value         = tostring(var.cloud_run_prod_min_instances)
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "cloud_run_prod_max_instances" {
  repository    = var.repository_name
  variable_name = "CLOUD_RUN_PROD_MAX_INSTANCES"
  value         = tostring(var.cloud_run_prod_max_instances)
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "agent_runtime_staging_min_instances" {
  repository    = var.repository_name
  variable_name = "AGENT_RUNTIME_STAGING_MIN_INSTANCES"
  value         = tostring(var.agent_runtime_staging_min_instances)
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "agent_runtime_staging_max_instances" {
  repository    = var.repository_name
  variable_name = "AGENT_RUNTIME_STAGING_MAX_INSTANCES"
  value         = tostring(var.agent_runtime_staging_max_instances)
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "agent_runtime_prod_min_instances" {
  repository    = var.repository_name
  variable_name = "AGENT_RUNTIME_PROD_MIN_INSTANCES"
  value         = tostring(var.agent_runtime_prod_min_instances)
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "agent_runtime_prod_max_instances" {
  repository    = var.repository_name
  variable_name = "AGENT_RUNTIME_PROD_MAX_INSTANCES"
  value         = tostring(var.agent_runtime_prod_max_instances)
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "google_cloud_project" {
  repository    = var.repository_name
  variable_name = "GOOGLE_CLOUD_PROJECT"
  value         = var.cicd_runner_project_id
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "service_account_email" {
  repository    = var.repository_name
  variable_name = "SERVICE_ACCOUNT_EMAIL"
  value         = google_service_account.cicd_runner_sa.email
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "gcp_wif_provider" {
  repository    = var.repository_name
  variable_name = "GCP_WIF_PROVIDER"
  value         = "projects/${data.google_project.cicd_project.number}/locations/global/workloadIdentityPools/${google_iam_workload_identity_pool.github_pool.workload_identity_pool_id}/providers/${google_iam_workload_identity_pool_provider.github_provider.workload_identity_pool_provider_id}"
  depends_on    = [github_repository.repo, data.github_repository.existing_repo]
}

resource "github_actions_variable" "gemini_model" {
  repository    = var.repository_name
  variable_name = "GEMINI_MODEL"
  value         = var.model
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "google_genai_use_gca" {
  repository    = var.repository_name
  variable_name = "GOOGLE_GENAI_USE_GCA"
  value         = "false"
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "gemini_cli_version" {
  repository    = var.repository_name
  variable_name = "GEMINI_CLI_VERSION"
  value         = "latest"
  depends_on    = [github_repository.repo]
}

resource "github_actions_variable" "upload_artifacts" {
  repository    = var.repository_name
  variable_name = "UPLOAD_ARTIFACTS"
  value         = "true"
  depends_on    = [github_repository.repo]
}

resource "github_repository_environment" "production_environment" {
  repository  = var.repository_name
  environment = "production"
  depends_on  = [github_repository.repo, data.github_repository.existing_repo]

  deployment_branch_policy {
    protected_branches     = false
    custom_branch_policies = true
  }
}

