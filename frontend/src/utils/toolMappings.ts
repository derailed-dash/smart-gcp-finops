/**
 * Maps technical, cryptic tool names into user-friendly active operations descriptions.
 * Keeps raw technical logs intact inside detailed diagnostics traces while providing
 * clear visual context for operators in status badges.
 */
export const mapToolNameToFriendlyName = (name: string): string => {
  if (!name) return 'Active Operation';
  const clean = name.replace(/_mcp_server/g, '').replace(/mcp_/g, '').trim();
  if (!clean) return 'Active Operation';

  if (clean.includes('execute_sql') || clean.includes('execute_cached_bigquery_sql') || clean.includes('query')) {
    return 'Querying GCP Cost Database';
  }
  if (clean.includes('get_table_info') || clean.includes('get_table')) {
    return 'Retrieving BigQuery Table Schema';
  }
  if (clean.includes('get_dataset_info') || clean.includes('get_dataset')) {
    return 'Retrieving BigQuery Dataset Schema';
  }
  if (clean.includes('list_table_ids') || clean.includes('list_tables')) {
    return 'Discovering Billing Tables';
  }
  if (clean.includes('list_dataset_ids') || clean.includes('list_datasets')) {
    return 'Discovering BigQuery Datasets';
  }
  if (clean.includes('list_zombie_resources')) {
    return 'Scanning for Unused Zombie Assets';
  }
  if (clean.includes('get_cai_metadata')) {
    return 'Retrieving Real-Time Asset Metadata';
  }
  if (clean.includes('get_cai_history')) {
    return 'Auditing Configuration History';
  }
  if (clean.includes('search_all_resources')) {
    return 'Searching GCP Asset Inventory';
  }
  if (clean.includes('search_all_iam_policies')) {
    return 'Auditing IAM Permissions & Policies';
  }
  if (clean.includes('analyze_org_policies')) {
    return 'Auditing GCP Organization Policies';
  }
  if (clean.includes('get_precomputed_spend_analysis')) {
    return 'Analysing Spend and Cost Trends';
  }
  if (clean.includes('get_precomputed_root_cause')) {
    return 'Analysing Cost Spike Root Cause';
  }
  if (clean.includes('run_cost_forecast')) {
    return 'Calculating Cost Forecast';
  }
  if (clean.includes('billing_explorer')) {
    return 'Consulting Billing Explorer';
  }
  if (clean.includes('infrastructure_auditor')) {
    return 'Consulting Infrastructure Auditor';
  }
  if (clean.includes('cloud_advisor')) {
    return 'Consulting Cloud Advisor';
  }
  if (clean.includes('knowledge_assistant')) {
    return 'Consulting Knowledge Assistant';
  }
  if (clean.includes('root_cause_analyst')) {
    return 'Consulting Root Cause Analyst';
  }
  if (clean.includes('get_session_value')) {
    return 'Retrieving Session Context';
  }
  if (clean.includes('set_session_value')) {
    return 'Saving Session Context';
  }
  if (clean.includes('ask_cloud_assist') || clean.includes('get_recommendations')) {
    return 'Querying Gemini Cloud Assist';
  }
  if (clean.includes('search_documents')) {
    return 'Searching GCP Architecture Documentation';
  }
  if (clean.includes('answer_query')) {
    return 'Retrieving Grounded Architecture Answers';
  }
  if (clean.includes('fetch_docs') || clean.includes('get_documents') || clean.includes('list_doc_sources')) {
    return 'Retrieving Developer Documentation';
  }
  if (clean.includes('get_today_top_services_and_usage')) {
    return 'Discovering Today\'s Active Services';
  }
  if (clean.includes('investigate_today_service_logs')) {
    return 'Auditing Today\'s Service Logs';
  }
  if (clean.includes('finish_task')) {
    return 'Finalising Analysis';
  }

  return clean;
};
