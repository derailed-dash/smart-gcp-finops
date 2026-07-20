variable "project_name" {
  type        = string
  description = "Project name used as a base for resource naming"
}

variable "prod_project_id" {
  type        = string
  description = "**Production** Google Cloud Project ID for resource deployment."
}

variable "staging_project_id" {
  type        = string
  description = "**Staging** Google Cloud Project ID for resource deployment."
}

variable "cicd_runner_project_id" {
  type        = string
  description = "Google Cloud Project ID where CI/CD pipelines will execute."
}

variable "host_connection_name" {
  description = "Name of the host connection to create in Cloud Build"
  type        = string
}

variable "repository_name" {
  description = "Name of the repository you'd like to connect to Cloud Build"
  type        = string
}

variable "app_sa_roles" {
  description = "List of roles to assign to the application service account"
  type        = list(string)
  default = [
    "roles/aiplatform.user",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
    "roles/storage.admin",
    "roles/serviceusage.serviceUsageConsumer",
    "roles/bigquery.jobUser",
    "roles/cloudasset.viewer",
    "roles/geminicloudassist.user",
    "roles/cloudaicompanion.user",
    "roles/recommender.viewer",
  ]
}

# Grants permissions for the runner to function internally.
# Lets the runner build things
variable "cicd_roles" {
  description = "List of roles to assign to the CICD runner service account in the CICD project"
  type        = list(string)
  default = [
    "roles/run.invoker",
    "roles/storage.admin",
    "roles/aiplatform.user",
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
    "roles/artifactregistry.writer",
    "roles/cloudbuild.builds.builder"
  ]
}

# Grants the cross-project permissions needed to actually deploy the application into those environments.
# Lets the runner deploy things
variable "cicd_sa_deployment_required_roles" {
  description = "List of roles to assign to the CICD runner service account for the Staging and Prod projects."
  type        = list(string)
  default = [
    "roles/run.admin",
    "roles/iam.serviceAccountUser",
    "roles/aiplatform.admin",
    "roles/agentregistry.admin",
    "roles/storage.admin"
  ]
}

variable "repository_owner" {
  description = "Owner of the Git repository - username or organization"
  type        = string
}

variable "create_repository" {
  description = "Flag indicating whether to create a new Git repository"
  type        = bool
}

variable "feedback_logs_filter" {
  type        = string
  description = "Log Sink filter for capturing feedback data. Captures logs where the `log_type` field is `feedback`."
}

variable "prod_app_domain_name" {
  description = "Custom domain mapped to the Production Cloud Run environment"
  type        = string
}

variable "staging_app_domain_name" {
  description = "Custom domain mapped to the Staging Cloud Run environment"
  type        = string
}

variable "cloud_run_staging_min_instances" {
  description = "Minimum number of instances for the Staging Cloud Run environment"
  type        = number
}

variable "cloud_run_staging_max_instances" {
  description = "Maximum number of instances for the Staging Cloud Run environment"
  type        = number
}

variable "cloud_run_prod_min_instances" {
  description = "Minimum number of instances for the Production Cloud Run environment"
  type        = number
}

variable "cloud_run_prod_max_instances" {
  description = "Maximum number of instances for the Production Cloud Run environment"
  type        = number
}

variable "agent_runtime_staging_min_instances" {
  description = "Minimum number of instances for the Staging Agent Runtime environment"
  type        = number
}

variable "agent_runtime_staging_max_instances" {
  description = "Maximum number of instances for the Staging Agent Runtime environment"
  type        = number
}

variable "agent_runtime_prod_min_instances" {
  description = "Minimum number of instances for the Production Agent Runtime environment"
  type        = number
}

variable "agent_runtime_prod_max_instances" {
  description = "Maximum number of instances for the Production Agent Runtime environment"
  type        = number
}

variable "iap_access_emails" {
  description = "List of emails to grant IAP access to"
  type        = list(string)
}

variable "google_cloud_billing_project" {
  type        = string
  description = "Google Cloud Project ID that hosts the BigQuery billing export data."
}

variable "billing_export_dataset" {
  type        = string
  description = "Name of the BigQuery dataset containing the billing export data."
}

variable "billing_account_id" {
  type        = string
  description = "The Google Cloud Billing Account ID (e.g., 1234FA-A1FF4E-6D5ED2)."
}

variable "billing_export_location" {
  type        = string
  description = "The Google Cloud Billing Export Location (e.g., europe-west4)."
}

variable "google_cloud_organization_id" {
  type        = string
  description = "The Google Cloud Organization ID (e.g., 123456789012)."
}

variable "google_genai_use_vertexai" {
  type        = bool
  description = "Flag indicating whether to use Vertex AI for Gemini"
  default     = true
}

variable "google_cloud_location" {
  type        = string
  description = "The Google Cloud location (region) for Gemini model calls"
  default     = "global"
}

variable "model" {
  type        = string
  description = "The primary Gemini model to use for agent reasoning"
}

variable "fast_model" {
  type        = string
  description = "The fast/lite Gemini model to use for semantic checks and routing"
}

variable "google_cloud_region" {
  type        = string
  description = "The Google Cloud region to use for model APIs"
  default     = "europe-west1"
}

variable "otel_to_cloud" {
  type        = bool
  description = "Whether to export OpenTelemetry traces to Cloud Trace"
  default     = true
}

variable "google_cloud_agent_engine_enable_telemetry" {
  type        = bool
  description = "Whether to enable agent engine telemetry"
  default     = true
}

variable "otel_semconv_stability_opt_in" {
  type        = string
  description = "OpenTelemetry semantic conventions opt-in level"
  default     = "gen_ai_latest_experimental"
}

variable "otel_instrumentation_genai_capture_message_content" {
  type        = string
  description = "OpenTelemetry GenAI message content capture mode"
  default     = "EVENT_ONLY"
}

