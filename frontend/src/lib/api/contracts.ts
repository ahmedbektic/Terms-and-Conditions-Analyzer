/* Architecture note:
 * Layer: transport contracts.
 * Keep field names aligned with backend JSON to avoid accidental drift.
 */

export interface AgreementCreateRequest {
  title?: string | null;
  source_url?: string | null;
  agreed_at?: string | null;
  terms_text: string;
}

export interface AgreementResponse {
  id: string;
  title: string | null;
  source_url: string | null;
  agreed_at: string | null;
  created_at: string;
}

export interface TrackedPolicyCreateRequest {
  source_url: string;
}

export interface TrackedPolicyResponse {
  id: string;
  canonical_url: string;
  display_name: string;
  source_type: string;
  tracking_status: string;
  last_checked_at: string | null;
  last_successful_capture_at: string | null;
  latest_capture_status: string;
  latest_capture_message: string | null;
  latest_change_status: string;
  latest_change_detected_at: string | null;
  created_at: string;
  snapshot_version_count: number;
}

export interface TrackedPolicyCreateResponse extends TrackedPolicyResponse {
  baseline_report_id: string;
  baseline_report_action: 'created' | 'reused';
}

export interface TrackedPolicyCheckExecutionResponse {
  id: string;
  tracked_policy_id: string;
  status: string; // 'pending' | 'running' | 'succeeded' | 'failed' | 'timed_out'
  result_snapshot_created: boolean | null;
  failure_message: string | null;
  execute_started_at: string | null;
  execute_finished_at: string | null;
}

export interface TrackedPolicyCheckExecutionEnvelope {
  execution: TrackedPolicyCheckExecutionResponse;
  tracked_policy: TrackedPolicyResponse | null;
}

export interface TrackedPolicySnapshotResponse {
  snapshot_id: string;
  version_number: number;
  captured_at: string;
  source_url: string | null;
  final_url: string | null;
  capture_status: string;
  change_status: string | null;
}

export interface TrackedPolicySnapshotCompareBlockResponse {
  change_type: 'unchanged' | 'added' | 'removed';
  older_text: string | null;
  newer_text: string | null;
}

export interface TrackedPolicySnapshotComparisonResponse {
  tracked_policy: TrackedPolicyResponse;
  older_snapshot: TrackedPolicySnapshotResponse;
  newer_snapshot: TrackedPolicySnapshotResponse;
  diff_blocks: TrackedPolicySnapshotCompareBlockResponse[];
  comparison_outcome: 'meaningful_changes' | 'no_meaningful_changes';
  normalization_notice: string | null;
  render_mode: 'split_or_unified';
}

export interface AnalysisTriggerRequest {
  trigger: 'manual';
}

export interface ReportAnalyzeRequest {
  title?: string | null;
  source_url?: string | null;
  agreed_at?: string | null;
  terms_text?: string | null;
}

export interface FlaggedClauseResponse {
  clause_type: string;
  severity: string;
  excerpt: string;
  explanation: string;
}

export interface ReportResponse {
  id: string;
  agreement_id: string;
  source_type: string;
  source_value: string;
  raw_input_excerpt: string;
  status: string;
  summary: string;
  trust_score: number;
  model_name: string;
  flagged_clauses: FlaggedClauseResponse[];
  created_at: string;
  completed_at: string | null;
  tracked_policy_id: string | null;
  tracked_policy_snapshot_id: string | null;
  tracked_policy_version_number: number | null;
}

export interface ReportListItemResponse {
  id: string;
  agreement_id: string;
  source_type: string;
  source_value: string;
  status: string;
  trust_score: number;
  model_name: string;
  created_at: string;
  tracked_policy_id: string | null;
  tracked_policy_snapshot_id: string | null;
  tracked_policy_version_number: number | null;
}
