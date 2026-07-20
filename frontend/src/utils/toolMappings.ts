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
  if (clean.includes('list_zombie_resources')) {
    return 'Scanning for Unused Zombie Assets';
  }
  if (clean.includes('get_cai_metadata')) {
    return 'Retrieving Real-Time Asset Metadata';
  }
  if (clean.includes('get_cai_history')) {
    return 'Auditing Configuration History';
  }
  if (clean.includes('list_datasets')) {
    return 'Discovering BigQuery Datasets';
  }
  if (clean.includes('list_tables')) {
    return 'Discovering Billing Tables';
  }
  if (clean.includes('get_precomputed_spend_analysis')) {
    return 'Analysing Spend and Cost Trends';
  }
  if (clean.includes('get_precomputed_root_cause')) {
    return 'Analysing Cost Spike Root Cause';
  }

  return clean;
};
