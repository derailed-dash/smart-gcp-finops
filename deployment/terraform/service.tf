# Get project information to access the project number
data "google_project" "project" {
  for_each = local.deploy_project_ids

  project_id = local.deploy_project_ids[each.key]
}

resource "google_cloud_run_v2_service" "app" {
  for_each = local.deploy_project_ids

  name                = var.project_name
  location            = var.google_cloud_region
  project             = each.value
  deletion_protection = false
  ingress             = "INGRESS_TRAFFIC_ALL"
  iap_enabled         = true

  template {
    containers {
      # Placeholder, will be replaced by the CI/CD pipeline
      image = "us-docker.pkg.dev/cloudrun/container/hello"
      resources {
        limits = {
          cpu    = "1"
          memory = "2Gi"
        }
        cpu_idle          = true
        startup_cpu_boost = true
      }

      env {
        name  = "GOOGLE_CLOUD_PROJECT"
        value = each.value
      }

      env {
        name  = "GOOGLE_CLOUD_REGION"
        value = lookup(local.env_map, "GOOGLE_CLOUD_REGION", var.google_cloud_region)
      }

      env {
        name  = "LOGS_BUCKET_NAME"
        value = google_storage_bucket.logs_data_bucket[each.value].name
      }

      env {
        name  = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
        value = lookup(local.env_map, "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", each.key == "prod" ? "NO_CONTENT" : "true")
      }

      env {
        name  = "OTEL_SERVICE_NAME"
        value = lookup(local.env_map, "OTEL_SERVICE_NAME", "${var.project_name}-${each.key}")
      }

      env {
        name  = "GOOGLE_CLOUD_BILLING_PROJECT"
        value = lookup(local.env_map, "GOOGLE_CLOUD_BILLING_PROJECT", var.google_cloud_billing_project)
      }

      env {
        name  = "BILLING_EXPORT_DATASET"
        value = lookup(local.env_map, "BILLING_EXPORT_DATASET", var.billing_export_dataset)
      }

      env {
        name  = "GOOGLE_CLOUD_BILLING_ACCOUNT"
        value = lookup(local.env_map, "GOOGLE_CLOUD_BILLING_ACCOUNT", var.billing_account_id)
      }

      env {
        name  = "GOOGLE_CLOUD_BILLING_LOCATION"
        value = lookup(local.env_map, "GOOGLE_CLOUD_BILLING_LOCATION", var.billing_export_location)
      }

      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = lookup(local.env_map, "GOOGLE_GENAI_USE_VERTEXAI", tostring(var.google_genai_use_vertexai))
      }

      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = lookup(local.env_map, "GOOGLE_CLOUD_LOCATION", var.google_cloud_location)
      }

      env {
        name  = "MODEL"
        value = lookup(local.env_map, "MODEL", var.model)
      }

      env {
        name  = "FAST_MODEL"
        value = lookup(local.env_map, "FAST_MODEL", var.fast_model)
      }

      env {
        name  = "GOOGLE_CLOUD_ORGANIZATION"
        value = lookup(local.env_map, "GOOGLE_CLOUD_ORGANIZATION", var.google_cloud_organization_id)
      }

      env {
        name  = "AGENT_RUNTIME_ID"
        value = google_vertex_ai_reasoning_engine.agent_engine[each.key].id
      }
    }

    service_account                  = google_service_account.app_sa[each.key].email
    max_instance_request_concurrency = 40

    scaling {
      min_instance_count = local.cloud_run_min_instances[each.key]
      max_instance_count = local.cloud_run_max_instances[each.key]
    }

    session_affinity = true
  }

  traffic {
    type    = "TRAFFIC_TARGET_ALLOCATION_TYPE_LATEST"
    percent = 100
  }

  # This lifecycle block prevents Terraform from overwriting fields managed by Cloud Build
  # (image, environment variables, client metadata) during deployments.
  lifecycle {
    ignore_changes = [
      annotations,
      client,
      client_version,
      template[0].annotations,
      template[0].containers[0].image,
      template[0].containers[0].env
    ]
  }

  # Make dependencies conditional to avoid errors.
  depends_on = [
    google_project_service.deploy_project_services,
  ]
}

resource "google_cloud_run_domain_mapping" "app_domain_mapping" {
  for_each = local.deploy_project_ids

  name     = local.app_domain_names[each.key]
  project  = each.value
  location = google_cloud_run_v2_service.app[each.key].location

  metadata {
    namespace = data.google_project.project[each.key].project_id
  }

  spec {
    route_name = google_cloud_run_v2_service.app[each.key].name
  }
}

# ==============================================================================
# Vertex AI Agent Runtime / Reasoning Engine
# ==============================================================================

locals {
  dummy_source_b64 = trimspace(file("${path.module}/shared/dummy_source.b64"))
}

resource "google_vertex_ai_reasoning_engine" "agent_engine" {
  for_each = local.deploy_project_ids

  display_name = "${var.project_name}-backend"
  description  = "FinSavant Agent Runtime Backend"
  region       = var.google_cloud_region
  project      = each.value

  spec {
    agent_framework = "google-adk"
    service_account = google_service_account.app_sa[each.key].email

    deployment_spec {
      min_instances         = local.agent_runtime_min_instances[each.key]
      max_instances         = local.agent_runtime_max_instances[each.key]
      container_concurrency = 5

      resource_limits = {
        cpu    = local.agent_runtime_cpu
        memory = local.agent_runtime_memory
      }

      env {
        name  = "LOGS_BUCKET_NAME"
        value = google_storage_bucket.logs_data_bucket[each.value].name
      }

      env {
        name  = "GOOGLE_CLOUD_REGION"
        value = lookup(local.env_map, "GOOGLE_CLOUD_REGION", var.google_cloud_region)
      }

      env {
        name  = "GOOGLE_CLOUD_LOCATION"
        value = lookup(local.env_map, "GOOGLE_CLOUD_LOCATION", var.google_cloud_location)
      }

      env {
        name  = "GOOGLE_CLOUD_BILLING_PROJECT"
        value = lookup(local.env_map, "GOOGLE_CLOUD_BILLING_PROJECT", var.google_cloud_billing_project)
      }

      env {
        name  = "BILLING_EXPORT_DATASET"
        value = lookup(local.env_map, "BILLING_EXPORT_DATASET", var.billing_export_dataset)
      }

      env {
        name  = "GOOGLE_CLOUD_BILLING_ACCOUNT"
        value = lookup(local.env_map, "GOOGLE_CLOUD_BILLING_ACCOUNT", var.billing_account_id)
      }

      env {
        name  = "GOOGLE_CLOUD_BILLING_LOCATION"
        value = lookup(local.env_map, "GOOGLE_CLOUD_BILLING_LOCATION", var.billing_export_location)
      }

      env {
        name  = "GOOGLE_GENAI_USE_VERTEXAI"
        value = lookup(local.env_map, "GOOGLE_GENAI_USE_VERTEXAI", tostring(var.google_genai_use_vertexai))
      }

      env {
        name  = "MODEL"
        value = lookup(local.env_map, "MODEL", var.model)
      }

      env {
        name  = "FAST_MODEL"
        value = lookup(local.env_map, "FAST_MODEL", var.fast_model)
      }

      env {
        name  = "GOOGLE_CLOUD_ORGANIZATION"
        value = lookup(local.env_map, "GOOGLE_CLOUD_ORGANIZATION", var.google_cloud_organization_id)
      }

      env {
        name  = "OTEL_TO_CLOUD"
        value = lookup(local.env_map, "OTEL_TO_CLOUD", tostring(var.otel_to_cloud))
      }

      env {
        name  = "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY"
        value = lookup(local.env_map, "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY", tostring(var.google_cloud_agent_engine_enable_telemetry))
      }

      env {
        name  = "OTEL_SEMCONV_STABILITY_OPT_IN"
        value = lookup(local.env_map, "OTEL_SEMCONV_STABILITY_OPT_IN", var.otel_semconv_stability_opt_in)
      }

      env {
        name  = "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT"
        value = lookup(local.env_map, "OTEL_INSTRUMENTATION_GENAI_CAPTURE_MESSAGE_CONTENT", var.otel_instrumentation_genai_capture_message_content)
      }

      env {
        name  = "OTEL_SERVICE_NAME"
        value = lookup(local.env_map, "OTEL_SERVICE_NAME", "${var.project_name}-${each.key}-backend")
      }

      env {
        name  = "ADK_DEFAULT_APP_NAME"
        value = local.agent_name
      }
    }

    source_code_spec {
      inline_source {
        source_archive = local.dummy_source_b64
      }

      python_spec {
        entrypoint_module  = "app.agent_runtime_app"
        entrypoint_object  = "agent_runtime"
        requirements_file  = "app/${local.agent_name}/requirements.txt"
        version            = "3.12"
      }
    }
  }

  lifecycle {
    ignore_changes = [
      spec,
    ]
  }

  depends_on = [
    google_project_service.deploy_project_services,
  ]
}

