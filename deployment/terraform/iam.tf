# Data source to get project numbers
data "google_project" "projects" {
  for_each   = local.deploy_project_ids
  project_id = each.value
}

# 1. Assign roles for the CICD project
resource "google_project_iam_member" "cicd_project_roles" {
  for_each = toset(var.cicd_roles)

  project    = var.cicd_runner_project_id
  role       = each.value
  member     = "serviceAccount:${resource.google_service_account.cicd_runner_sa.email}"
  depends_on = [resource.google_project_service.cicd_services, resource.google_project_service.deploy_project_services]
}

# 2. Assign roles for the other two projects (prod and staging)
resource "google_project_iam_member" "other_projects_roles" {
  for_each = {
    for pair in setproduct(keys(local.deploy_project_ids), var.cicd_sa_deployment_required_roles) :
    "${pair[0]}-${pair[1]}" => {
      project_id = local.deploy_project_ids[pair[0]]
      role       = pair[1]
    }
  }

  project    = each.value.project_id
  role       = each.value.role
  member     = "serviceAccount:${resource.google_service_account.cicd_runner_sa.email}"
  depends_on = [resource.google_project_service.cicd_services, resource.google_project_service.deploy_project_services]
}
# 3. Grant application SA the required permissions to run the application
resource "google_project_iam_member" "app_sa_roles" {
  for_each = {
    for pair in setproduct(keys(local.deploy_project_ids), var.app_sa_roles) :
    join(",", pair) => {
      project = local.deploy_project_ids[pair[0]]
      role    = pair[1]
    }
  }

  project    = each.value.project
  role       = each.value.role
  member     = "serviceAccount:${google_service_account.app_sa[split(",", each.key)[0]].email}"
  depends_on = [resource.google_project_service.cicd_services, resource.google_project_service.deploy_project_services]
}

# 4. Allow Cloud Run service SA to pull containers stored in the CICD project
resource "google_project_iam_member" "cicd_run_invoker_artifact_registry_reader" {
  for_each = local.deploy_project_ids
  project  = var.cicd_runner_project_id

  role       = "roles/artifactregistry.reader"
  member     = "serviceAccount:service-${data.google_project.projects[each.key].number}@serverless-robot-prod.iam.gserviceaccount.com"
  depends_on = [resource.google_project_service.cicd_services, resource.google_project_service.deploy_project_services]

}

# Special assignment: Allow the CICD SA to create tokens
resource "google_service_account_iam_member" "cicd_run_invoker_token_creator" {
  service_account_id = google_service_account.cicd_runner_sa.name
  role               = "roles/iam.serviceAccountTokenCreator"
  member             = "serviceAccount:${resource.google_service_account.cicd_runner_sa.email}"
  depends_on         = [resource.google_project_service.cicd_services, resource.google_project_service.deploy_project_services]
}
# Special assignment: Allow the CICD SA to impersonate itself for trigger creation
resource "google_service_account_iam_member" "cicd_run_invoker_account_user" {
  service_account_id = google_service_account.cicd_runner_sa.name
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${resource.google_service_account.cicd_runner_sa.email}"
  depends_on         = [resource.google_project_service.cicd_services, resource.google_project_service.deploy_project_services]
}

# Grant specific users access to pass through IAP to the Cloud Run service
resource "google_iap_web_cloud_run_service_iam_binding" "iap_users" {
  for_each = local.deploy_project_ids

  project                = google_cloud_run_v2_service.app[each.key].project
  location               = google_cloud_run_v2_service.app[each.key].location
  cloud_run_service_name = google_cloud_run_v2_service.app[each.key].name
  role                   = "roles/iap.httpsResourceAccessor"

  members = [for email in var.iap_access_emails : "user:${email}"]
}

resource "google_project_service_identity" "iap_sa" {
  provider = google-beta
  for_each = local.deploy_project_ids

  project = each.value
  service = "iap.googleapis.com"
}

# Allow the Google IAP Service Agent to invoke the Cloud Run service
resource "google_cloud_run_v2_service_iam_member" "iap_invoker" {
  for_each = local.deploy_project_ids

  project  = google_cloud_run_v2_service.app[each.key].project
  location = google_cloud_run_v2_service.app[each.key].location
  name     = google_cloud_run_v2_service.app[each.key].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_project_service_identity.iap_sa[each.key].email}"
}

# 5. Grant application SA the required permissions to access billing data in the billing project
resource "google_project_iam_member" "billing_project_access" {
  for_each = {
    for pair in setproduct(keys(local.deploy_project_ids), ["roles/bigquery.dataViewer", "roles/bigquery.jobUser"]) :
    "${pair[0]}-${pair[1]}" => {
      env  = pair[0]
      role = pair[1]
    }
  }

  project = var.google_cloud_billing_project
  role    = each.value.role
  member  = "serviceAccount:${google_service_account.app_sa[each.value.env].email}"
}

# 6. Grant application SA the ability to list projects for the billing account
resource "google_billing_account_iam_member" "billing_account_viewer" {
  for_each = local.deploy_project_ids

  billing_account_id = var.billing_account_id
  role               = "roles/billing.viewer"
  member             = "serviceAccount:${google_service_account.app_sa[each.key].email}"
}

# 7. (Optional) Grant application SA Organization-level Asset Viewer for efficient Org-wide discovery
resource "google_organization_iam_member" "organization_asset_viewer" {
  for_each = {
    for env in keys(local.deploy_project_ids) : env => env
    if var.google_cloud_organization_id != ""
  }

  org_id = var.google_cloud_organization_id
  role   = "roles/cloudasset.viewer"
  member = "serviceAccount:${google_service_account.app_sa[each.key].email}"
}
